"""
Setup script for creating a standalone Mac app
Run: python3 setup_mac_app.py py2app
"""
from setuptools import setup

APP = ['menu_bar_app.py']
DATA_FILES = [
    ('', ['crono_knowledge_base.txt']),
    ('', ['.env']),
]
OPTIONS = {
    'argv_emulation': False,
    'iconfile': None,
    'plist': {
        'CFBundleName': 'Crono Follow-up',
        'CFBundleDisplayName': 'Crono Meeting Follow-up',
        'CFBundleIdentifier': 'com.crono.followup',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'LSUIElement': True,  # Makes it a menu bar app (no dock icon)
        'LSBackgroundOnly': False,
    },
    'packages': [
        'rumps',
        'requests',
        'anthropic',
        'google.generativeai',
        'google.auth',
        'google.oauth2',
        'googleapiclient',
        'dateutil',
        'pytz',
        'dotenv',
    ],
    'includes': [
        'modules.fathom_client',
        'modules.claude_email_generator',
        'modules.gemini_email_generator',
        'modules.gmail_draft_creator',
        'modules.date_extractor',
        'modules.calendar_event_creator',
        'modules.meeting_summary_generator',
        'modules.sales_summary_generator',
        'modules.crono_client',
    ],
}

setup(
    name='Crono Follow-up',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
