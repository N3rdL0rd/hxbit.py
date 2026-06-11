from __future__ import annotations

import os
import reprlib
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict

from .core import HXSFile, Obj

if os.name == "nt":
    from hidpi_tk import DPIAwareTk
else:
    DPIAwareTk = tk.Tk


def _fix_hidpi_linux(root: tk.Tk) -> float:
    """Scale Tk fonts and widget sizing to match the screen's actual DPI.

    Tk defaults to assuming 96 DPI on X11/Wayland, which looks tiny on HiDPI
    displays. ``HXBIT_UI_SCALE`` can be set to override the detected scaling
    factor for setups where the reported DPI is wrong.

    Returns the scaling factor that was applied (1.0 if none).
    """
    override = os.environ.get("HXBIT_UI_SCALE")
    if override:
        try:
            scaling = float(override)
        except ValueError:
            scaling = 1.0
    else:
        # Tk's own DPI guess (winfo_fpixels) relies on the X server's
        # configured Xft.dpi, which is often left at the 96 default even on
        # HiDPI screens. Cross-check against the screen's physical size,
        # which X11/Wayland usually report correctly from the monitor's EDID.
        scaling = root.winfo_fpixels("1i") / 72.0

        mm_w, mm_h = root.winfo_screenmmwidth(), root.winfo_screenmmheight()
        if mm_w > 0 and mm_h > 0:
            px_w, px_h = root.winfo_screenwidth(), root.winfo_screenheight()
            physical_dpi = ((px_w / (mm_w / 25.4)) + (px_h / (mm_h / 25.4))) / 2
            scaling = max(scaling, physical_dpi / 72.0)

    if scaling <= 1.01:
        return 1.0

    root.tk.call("tk", "scaling", scaling)

    # "tk scaling" mainly affects ttk theme metrics specified in points
    # (hence borders/padding growing). Named fonts realized at startup don't
    # reliably re-render bigger just from a scaling change, so force their
    # pixel size directly: negative size = literal pixels, so this bypasses
    # any point->pixel conversion entirely.
    import tkinter.font

    available = {f.lower() for f in tkinter.font.families(root)}

    def _pick(*preferred: str) -> str | None:
        for fam in preferred:
            if fam.lower() in available:
                return fam
        return None

    sans_fallback = _pick("DejaVu Sans", "Liberation Sans", "Noto Sans", "Helvetica", "Arial")
    mono_fallback = _pick("DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono", "Courier New", "Courier")

    for name in tkinter.font.names(root):
        font = tkinter.font.Font(root=root, name=name, exists=True)
        size = int(font["size"])
        px = -size if size < 0 else round(size * 96 / 72)
        new_size = -round(px * scaling)
        if font.actual("family").lower() == "fixed":
            # Some minimal X setups fall back to the legacy "fixed" bitmap
            # font, which ignores size requests entirely. Swap to a
            # scalable family so the size change actually takes effect.
            fallback = mono_fallback if "fixed" in name.lower() else sans_fallback
            if fallback:
                font.configure(family=fallback, size=new_size)
            else:
                font["size"] = new_size
        else:
            font["size"] = new_size

    # ttk.Treeview's row height is a fixed pixel value baked into the theme
    # at its original 96dpi assumption, so it doesn't grow with the font and
    # rows start overlapping. Resize it to fit the now-larger default font.
    default_font = tkinter.font.nametofont("TkDefaultFont")
    row_height = default_font.metrics("linespace") + round(4 * scaling)
    style = ttk.Style(root)
    style.configure("Treeview", rowheight=row_height)

    return scaling


ScalarTypeName = str


def _format_scalar(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "None"
    return str(value)


def _value_kind(value: Any) -> str:
    if isinstance(value, Obj):
        return value.schema.classdef.name.value if value.schema.classdef else "Obj"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, list):
        return "list"
    if value is None:
        return "None"
    return type(value).__name__


def _value_summary(value: Any) -> str:
    if isinstance(value, Obj):
        return f"{_value_kind(value)} ({len(value.fields)} fields)"
    if isinstance(value, dict):
        return f"{len(value)} entries"
    if isinstance(value, list):
        return f"{len(value)} items"
    if isinstance(value, bytes):
        return f"{len(value)} bytes"
    if isinstance(value, str):
        return value if len(value) <= 200 else value[:200] + "…"
    if value is None:
        return "None"
    return str(value)


class HXSFileEditor(DPIAwareTk):
    def __init__(self, initial_path: str | None = None, initial_shims: str = "deadcells"):
        super().__init__()
        scaling = 1.0
        if os.name != "nt":
            scaling = _fix_hidpi_linux(self)
        self.title("hxbit editor")
        self.geometry(f"{round(1200 * scaling)}x{round(800 * scaling)}")

        self.current_path: Path | None = None
        self.current_file: HXSFile | None = None
        self.node_meta: Dict[str, Dict[str, Any]] = {}

        self.shims_var = tk.StringVar(value=initial_shims)
        self.status_var = tk.StringVar(value="Ready")
        self.selected_item: str | None = None
        self.edit_type_var = tk.StringVar(value="str")
        self.edit_value_var = tk.StringVar()

        self._build_ui()

        if initial_path:
            self.open_path(Path(initial_path))

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=8)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(6, weight=1)

        ttk.Button(toolbar, text="Open", command=self.open_dialog).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(toolbar, text="Save", command=self.save_current).grid(row=0, column=1, padx=6)
        ttk.Button(toolbar, text="Save As", command=self.save_as_dialog).grid(row=0, column=2, padx=6)
        ttk.Label(toolbar, text="Shims").grid(row=0, column=3, padx=(18, 6))
        ttk.Entry(toolbar, textvariable=self.shims_var, width=20).grid(row=0, column=4, padx=6)
        ttk.Button(toolbar, text="Reload", command=self.reload_current).grid(row=0, column=5, padx=6)

        self.path_label = ttk.Label(toolbar, text="No file loaded")
        self.path_label.grid(row=0, column=6, sticky="ew", padx=(18, 0))

        notebook = ttk.Notebook(self)
        notebook.grid(row=1, column=0, sticky="nsew")

        summary_frame = ttk.Frame(notebook, padding=8)
        schemas_frame = ttk.Frame(notebook, padding=8)
        object_frame = ttk.Frame(notebook, padding=8)

        notebook.add(summary_frame, text="Summary")
        notebook.add(schemas_frame, text="Schemas")
        notebook.add(object_frame, text="Object")

        summary_frame.columnconfigure(0, weight=1)
        summary_frame.rowconfigure(0, weight=1)
        self.summary_text = tk.Text(summary_frame, wrap="word")
        self.summary_text.grid(row=0, column=0, sticky="nsew")
        self.summary_text.configure(state="disabled")

        schemas_frame.columnconfigure(0, weight=1)
        schemas_frame.rowconfigure(0, weight=1)
        self.schemas_text = tk.Text(schemas_frame, wrap="none")
        self.schemas_text.grid(row=0, column=0, sticky="nsew")
        self.schemas_text.configure(state="disabled")

        object_frame.columnconfigure(0, weight=1)
        object_frame.rowconfigure(0, weight=1)
        object_pane = ttk.Panedwindow(object_frame, orient="horizontal")
        object_pane.grid(row=0, column=0, sticky="nsew")

        tree_frame = ttk.Frame(object_pane, padding=(0, 0, 8, 0))
        detail_frame = ttk.Frame(object_pane)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        detail_frame.columnconfigure(1, weight=1)
        detail_frame.rowconfigure(5, weight=1)

        self.object_tree = ttk.Treeview(tree_frame, columns=("kind", "value"), show="tree headings")
        self.object_tree.heading("#0", text="Path")
        self.object_tree.heading("kind", text="Kind")
        self.object_tree.heading("value", text="Value")
        self.object_tree.column("#0", width=320, stretch=True)
        self.object_tree.column("kind", width=160, stretch=False)
        self.object_tree.column("value", width=320, stretch=True)
        self.object_tree.grid(row=0, column=0, sticky="nsew")
        self.object_tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.object_tree.bind("<<TreeviewOpen>>", self.on_tree_open)

        object_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.object_tree.yview)
        object_scroll.grid(row=0, column=1, sticky="ns")
        self.object_tree.configure(yscrollcommand=object_scroll.set)

        object_pane.add(tree_frame, weight=3)
        object_pane.add(detail_frame, weight=2)

        self.object_info = tk.Text(detail_frame, height=14, wrap="word")
        self.object_info.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
        self.object_info.configure(state="disabled")

        ttk.Label(detail_frame, text="Scalar Type").grid(row=1, column=0, sticky="w", pady=4)
        self.type_combo = ttk.Combobox(
            detail_frame,
            textvariable=self.edit_type_var,
            values=("str", "int", "float", "bool", "None"),
            state="readonly",
        )
        self.type_combo.grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(detail_frame, text="Value").grid(row=2, column=0, sticky="w", pady=4)
        self.value_entry = ttk.Entry(detail_frame, textvariable=self.edit_value_var)
        self.value_entry.grid(row=2, column=1, sticky="ew", pady=4)

        self.apply_button = ttk.Button(detail_frame, text="Apply", command=self.apply_edit)
        self.apply_button.grid(row=3, column=1, sticky="e", pady=(8, 0))

        status = ttk.Label(self, textvariable=self.status_var, anchor="w", padding=8)
        status.grid(row=2, column=0, sticky="ew")

        self._set_text(self.summary_text, "Open an HXS file to inspect it.")
        self._set_text(self.schemas_text, "")
        self._set_text(self.object_info, "No object selected.")
        self._set_editor_enabled(False)

    def _set_text(self, widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _set_editor_enabled(self, enabled: bool) -> None:
        state = "readonly" if enabled else "disabled"
        entry_state = "normal" if enabled else "disabled"
        button_state = "normal" if enabled else "disabled"
        self.type_combo.configure(state=state)
        self.value_entry.configure(state=entry_state)
        self.apply_button.configure(state=button_state)

    def open_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open HXS file",
            filetypes=[("Hxbit files", "*.bin *.dat"), ("All files", "*.*")],
        )
        if path:
            self.open_path(Path(path))

    def open_path(self, path: Path) -> None:
        try:
            hxs = HXSFile(shims=self.shims_var.get() or None)
            with path.open("rb") as f:
                hxs.deserialise(f)
        except Exception as e:
            messagebox.showerror("Open failed", str(e))
            self.status_var.set(f"Failed to open {path.name}")
            return

        self.current_path = path
        self.current_file = hxs
        self.path_label.configure(text=str(path))
        self._refresh_views()
        self.status_var.set(f"Loaded {path.name}")
        self.title(f"hxbit editor - {path.name}")

    def reload_current(self) -> None:
        if self.current_path is None:
            self.open_dialog()
            return
        self.open_path(self.current_path)

    def save_current(self) -> None:
        if self.current_file is None:
            return
        if self.current_path is None:
            self.save_as_dialog()
            return
        try:
            self.current_path.write_bytes(self.current_file.serialise())
        except Exception as e:
            messagebox.showerror("Save failed", str(e))
            self.status_var.set(f"Failed to save {self.current_path.name}")
            return
        self.status_var.set(f"Saved {self.current_path.name}")

    def save_as_dialog(self) -> None:
        if self.current_file is None:
            return
        path = filedialog.asksaveasfilename(
            title="Save HXS file",
            defaultextension=".bin",
            filetypes=[("Hxbit files", "*.bin *.dat"), ("All files", "*.*")],
        )
        if not path:
            return
        self.current_path = Path(path)
        self.save_current()
        self.path_label.configure(text=str(self.current_path))
        self.title(f"hxbit editor - {self.current_path.name}")

    def _refresh_views(self) -> None:
        assert self.current_file is not None
        hxs = self.current_file

        summary_lines = [
            f"Magic: {hxs.magic.value}",
            f"Version: {hxs.version.value}",
            f"Class definitions: {len(hxs.classdefs)}",
            f"Schemas: {len(hxs.schemas)}",
            f"Parsed objects: {len(hxs.objects)}",
            f"Root object parsed: {'yes' if hxs.obj is not None else 'no'}",
            f"Raw object payload preserved: {'yes' if hxs.raw_object_data is not None else 'no'}",
        ]
        if hxs.obj and hxs.obj.schema.classdef:
            summary_lines.append(f"Root class: {hxs.obj.schema.classdef.name.value}")
        if hxs.object_parse_error is not None:
            summary_lines.append("")
            summary_lines.append("Object parse warning:")
            summary_lines.append(str(hxs.object_parse_error))
        self._set_text(self.summary_text, "\n".join(summary_lines))
        self._set_text(self.schemas_text, hxs.pprint_classdefs() + "\n\n" + hxs.pprint_schemas())

        self.object_tree.delete(*self.object_tree.get_children())
        self.node_meta.clear()
        self.selected_item = None

        if hxs.obj is None:
            message = "Typed root object parsing is not available for this file.\n\n"
            if hxs.object_parse_error is not None:
                message += f"Reason: {hxs.object_parse_error}\n\n"
            message += "The file can still be saved losslessly because the raw object payload is preserved."
            self._set_text(self.object_info, message)
            self._set_editor_enabled(False)
            return

        root_name = hxs.obj.schema.classdef.name.value if hxs.obj.schema.classdef else "Root"
        root_id = self.object_tree.insert(
            "",
            "end",
            text=root_name,
            values=(_value_kind(hxs.obj), _value_summary(hxs.obj)),
            open=True,
        )
        self.node_meta[root_id] = {
            "value": hxs.obj,
            "container": None,
            "key": None,
            "path": root_name,
            "ancestors": frozenset({id(hxs.obj)}),
            "populated": False,
        }
        self._populate_children(root_id)
        self.object_tree.selection_set(root_id)
        self.object_tree.focus(root_id)
        self.on_tree_select()

    # The object graph is heavily cross-linked (thousands of objects, where
    # e.g. every entity points back at the level and the level at every
    # entity), so eagerly expanding it into the tree explodes combinatorially.
    # Children are therefore only materialized when a node is opened, with a
    # placeholder child standing in until then.
    _PLACEHOLDER_TEXT = "…"

    @staticmethod
    def _is_expandable(value: Any) -> bool:
        if isinstance(value, Obj):
            return bool(value.fields)
        if isinstance(value, (dict, list)):
            return bool(value)
        return False

    def _iter_children(self, value: Any) -> list[tuple[str, str, Any, Any]]:
        """Yields (label, path_suffix, key, child) for one level of `value`."""
        if isinstance(value, Obj):
            return [(key, f".{key}", key, child) for key, child in value.fields.items()]
        if isinstance(value, dict):
            return [(repr(key), f"[{key!r}]", key, child) for key, child in value.items()]
        if isinstance(value, list):
            return [(f"[{i}]", f"[{i}]", i, child) for i, child in enumerate(value)]
        return []

    def _populate_children(self, parent: str) -> None:
        meta = self.node_meta[parent]
        if meta.get("populated") or meta.get("is_cycle"):
            return
        meta["populated"] = True
        for placeholder in self.object_tree.get_children(parent):
            if placeholder not in self.node_meta:
                self.object_tree.delete(placeholder)

        value = meta["value"]
        ancestors: frozenset[int] = meta["ancestors"]
        container = value.fields if isinstance(value, Obj) else value
        for label, suffix, key, child in self._iter_children(value):
            is_container = isinstance(child, (Obj, dict, list))
            is_cycle = is_container and id(child) in ancestors
            child_id = self.object_tree.insert(
                parent,
                "end",
                text=label,
                values=(
                    _value_kind(child),
                    "<circular reference>" if is_cycle else _value_summary(child),
                ),
                open=False,
            )
            self.node_meta[child_id] = {
                "value": child,
                "container": container,
                "key": key,
                "path": meta["path"] + suffix,
                "is_cycle": is_cycle,
                "ancestors": ancestors | {id(child)} if is_container else ancestors,
                "populated": False,
            }
            if not is_cycle and self._is_expandable(child):
                self.object_tree.insert(child_id, "end", text=self._PLACEHOLDER_TEXT)

    def on_tree_open(self, _event: tk.Event | None = None) -> None:
        item_id = self.object_tree.focus()
        if item_id in self.node_meta:
            self._populate_children(item_id)

    def on_tree_select(self, _event: tk.Event | None = None) -> None:
        selected = self.object_tree.selection()
        if not selected:
            return
        item_id = selected[0]
        if item_id not in self.node_meta:  # lazy-expansion placeholder
            return
        self.selected_item = item_id
        meta = self.node_meta[item_id]
        value = meta["value"]

        lines = [
            f"Path: {meta['path']}",
            f"Kind: {_value_kind(value)}",
            f"Summary: {_value_summary(value)}",
        ]
        if meta.get("is_cycle"):
            lines.append("")
            lines.append("Circular reference. Expansion stops here.")
            self._set_text(self.object_info, "\n".join(lines))
            self._set_editor_enabled(False)
            return
        if isinstance(value, Obj):
            lines.append("")
            detail = value.pprint()
            if len(detail) > 200_000:
                detail = detail[:200_000] + "\n… (truncated; expand the tree to inspect nested values)"
            lines.append(detail)
            self._set_editor_enabled(False)
        elif isinstance(value, (dict, list)):
            lines.append("")
            # Bounded repr: shared sub-objects make a full repr explode.
            lines.append(reprlib.Repr(maxlevel=3, maxdict=20, maxlist=20, maxstring=120, maxother=120).repr(value))
            self._set_editor_enabled(False)
        else:
            lines.append("")
            lines.append("Editable scalar value.")
            scalar_type = self._scalar_type_name(value)
            self.edit_type_var.set(scalar_type)
            self.edit_value_var.set("" if value is None else _format_scalar(value))
            self._set_editor_enabled(True)

        self._set_text(self.object_info, "\n".join(lines))

    def _scalar_type_name(self, value: Any) -> ScalarTypeName:
        if value is None:
            return "None"
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        return "str"

    def _parse_scalar(self, type_name: ScalarTypeName, raw: str) -> Any:
        if type_name == "None":
            return None
        if type_name == "bool":
            lowered = raw.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
            raise ValueError("Boolean values must be true/false, yes/no, on/off, or 1/0.")
        if type_name == "int":
            return int(raw, 0)
        if type_name == "float":
            return float(raw)
        return raw

    def apply_edit(self) -> None:
        if self.current_file is None or self.selected_item is None:
            return
        meta = self.node_meta[self.selected_item]
        container = meta["container"]
        key = meta["key"]
        if container is None:
            return

        try:
            new_value = self._parse_scalar(self.edit_type_var.get(), self.edit_value_var.get())
        except Exception as e:
            messagebox.showerror("Invalid value", str(e))
            return

        container[key] = new_value
        meta["value"] = new_value
        self.current_file.object_parse_error = None
        self.current_file.raw_object_data = None

        self.object_tree.item(
            self.selected_item,
            values=(_value_kind(new_value), _value_summary(new_value)),
        )
        self.on_tree_select()
        self.status_var.set("Applied edit")


def launch_gui(initial_path: str | None = None, initial_shims: str = "deadcells") -> None:
    app = HXSFileEditor(initial_path=initial_path, initial_shims=initial_shims)
    app.mainloop()
