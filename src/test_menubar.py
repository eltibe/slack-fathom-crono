#!/usr/bin/env python3
"""
Simple test to verify menu bar app works
"""
import rumps

class TestApp(rumps.App):
    def __init__(self):
        super(TestApp, self).__init__("TEST", quit_button="Quit")

    @rumps.clicked("Say Hello")
    def say_hello(self, _):
        rumps.alert("Hello!", "The menu bar app is working!")

if __name__ == "__main__":
    print("Starting test menu bar app...")
    print("Look for 'TEST' in your menu bar")
    print("If you see it, the menu bar system works!")
    TestApp().run()
