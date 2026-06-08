#!/usr/bin/env python3
"""Plugin TV basique"""
class TVPlugin:
    def __init__(self, manager): self.manager = manager; self.devices = {}
    def add_device(self, name, config): self.devices[name] = config
    def turn_on(self, name=None): print(f"TV ON: {name}"); return True
    def turn_off(self, name=None): print(f"TV OFF: {name}"); return True
    def toggle(self, name=None): print(f"TV TOGGLE: {name}"); return True
    def volume_up(self, name=None): print("VOL+"); return True
    def volume_down(self, name=None): print("VOL-"); return True
    def mute(self, name=None): print("MUTE"); return True
    def netflix(self, name=None): print("NETFLIX"); return True
    def youtube(self, name=None): print("YOUTUBE"); return True