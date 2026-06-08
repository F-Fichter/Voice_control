#!/usr/bin/env python3
"""Plugin HTTP générique"""
import requests
class HttpPlugin:
    def __init__(self, manager): self.manager = manager; self.devices = {}
    def add_device(self, name, config): self.devices[name] = config
    def turn_on(self, name=None): print(f"HTTP ON: {name}"); return True
    def turn_off(self, name=None): print(f"HTTP OFF: {name}"); return True
    def toggle(self, name=None): print(f"HTTP TOGGLE: {name}"); return True
    def get_status(self, name=None): return {"status": "ok"}