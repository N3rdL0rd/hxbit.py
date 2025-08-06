"""
Type shims for Dead Cells save file data.
"""

TYPES = {
    "tool.bossRush.BossRushData.unlockedGameMode": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "idx": {"type": "Int"},
                "unlock": {"type": "Bool"}
            }
        }
    },
    "tool.bossRush.BossRushData.basementUnlock": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "idx": {"type": "Int"},
                "unlock": {"type": "Bool"}
            }
        }
    },
    "tool.bossRush.BossRushData.capUnlock": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "idx": {"type": "Int"},
                "unlock": {"type": "Bool"}
            }
        }
    },
    "tool.bossRush.BossRushData.pantUnlock": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "idx": {"type": "Int"},
                "unlock": {"type": "Bool"}
            }
        }
    },
    "tool.bossRush.BossRushData.skirtUnlock": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "idx": {"type": "Int"},
                "unlock": {"type": "Bool"}
            }
        }
    },
    "tool.bossRush.BossRushData.skullUnlock": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "idx": {"type": "Int"},
                "unlock": {"type": "Bool"}
            }
        }
    },
    "tool.bossRush.BossRushData.topUnlock": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "idx": {"type": "Int"},
                "unlock": {"type": "Bool"}
            }
        }
    },
    "tool.bossRush.BossRushData.weaponUnlock": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "idx": {"type": "Int"},
                "unlock": {"type": "Bool"}
            }
        }
    },
    "tool.bossRush.BossRushData.materialUnlock": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "idx": {"type": "Int"},
                "unlock": {"type": "Bool"}
            }
        }
    },
    "tool.SpeedrunData.bestRunTime": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "bc": {"type": "Int"},
                "t": {"type": "Float"}
            }
        }
    },
    "tool.SpeedrunData.bestAnchoredTimePerLevel": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "id": {"type": "String"},
                "t": {"type": "Float"}
            }
        }
    },
    "tool.SpeedrunData.bestTimePerLevel": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "id": {"type": "String"},
                "t": {"type": "Float"}
            }
        }
    },
    "tool.SpeedrunData.runTimePerLevel": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "id": {"type": "String"},
                "t": {"type": "Float"}
            }
        }
    },
    "tool.SpeedrunData.anchoredRunLevelDelta": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "id": {"type": "String"},
                "t": {"type": "Float"}
            }
        }
    },
    "tool.SpeedrunData.runLevelDelta": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "id": {"type": "String"},
                "t": {"type": "Float"}
            }
        }
    },
    "UserStats.biomesTransitions": {
        "type": "Array",
        "payload": {
            "type": "Obj",
            "fields": {
                "from": {"type": "String"},
                "to": {"type": "String"}
            }
        }
    }
}