#!/usr/bin/env python3
"""Plugin vide pour ESP32 Relay"""
class ESP32RelayPlugin:
    def __init__(self, manager):
        self.manager = manager
        self.devices = {}
    def add_device(self, name, config): self.devices[name] = config
    def turn_on(self, name=None): print(f"ON: {name}"); return True
    def turn_off(self, name=None): print(f"OFF: {name}"); return True
    def toggle(self, name=None): print(f"TOGGLE: {name}"); return True
    def get_status(self, name=None): return {"online": True}