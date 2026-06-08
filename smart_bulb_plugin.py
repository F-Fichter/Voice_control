#!/usr/bin/env python3
"""Plugin Smart Bulb"""
class SmartBulbPlugin:
    def __init__(self, manager): self.manager = manager; self.devices = {}
    def add_device(self, name, config): self.devices[name] = config
    def turn_on(self, name=None): print(f"BULB ON: {name}"); return True
    def turn_off(self, name=None): print(f"BULB OFF: {name}"); return True
    def toggle(self, name=None): print(f"BULB TOGGLE: {name}"); return True
    def set_color(self, r, g, b, name=None): print(f"COLOR: {r},{g},{b}"); return True
    def get_status(self, name=None): return {"on": True}