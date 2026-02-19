#!/usr/bin/env python
"""
Pre-deployment verification script.
Checks if all required files and configurations are in place.
"""
import os
import sys
from pathlib import Path

def check_file_exists(filepath, description):
    """Check if a file exists."""
    if Path(filepath).exists():
        print(f"✅ {description}: {filepath}")
        return True
    else:
        print(f"❌ {description} MISSING: {filepath}")
        return False

def check_env_example():
    """Check if .env.example has all required variables."""
    required_vars = [
        'SECRET_KEY',
        'DEBUG',
        'ALLOWED_HOSTS',
        'DISCORD_TOKEN',
        'DISCORD_GUILD_ID',
        'DISCORD_FALLBACK_CATEGORY_ID'
    ]
    
    try:
        with open('.env.example', 'r', encoding='utf-8') as f:
            content = f.read()
            missing = []
            for var in required_vars:
                if var not in content:
                    missing.append(var)
            
            if missing:
                print(f"❌ .env.example missing variables: {', '.join(missing)}")
                return False
            else:
                print(f"✅ .env.example contains all required variables")
                return True
    except FileNotFoundError:
        print("❌ .env.example file not found")
        return False

def main():
    print("=" * 60)
    print("🔍 Eventometer Deployment Readiness Check")
    print("=" * 60)
    print()
    
    checks = []
    
    # Core files
    print("📁 Core Files:")
    checks.append(check_file_exists('manage.py', 'Django manage.py'))
    checks.append(check_file_exists('requirements.txt', 'Requirements'))
    checks.append(check_file_exists('eventometer/settings.py', 'Settings'))
    print()
    
    # Deployment files
    print("🚂 Railway Deployment Files:")
    checks.append(check_file_exists('Procfile', 'Procfile'))
    checks.append(check_file_exists('railway.json', 'Railway config'))
    checks.append(check_file_exists('nixpacks.toml', 'Nixpacks config'))
    checks.append(check_file_exists('runtime.txt', 'Python runtime'))
    print()
    
    # Documentation
    print("📚 Documentation:")
    checks.append(check_file_exists('DEPLOY.md', 'Deployment guide'))
    checks.append(check_file_exists('DEPLOYMENT_CHECKLIST.md', 'Deployment checklist'))
    checks.append(check_file_exists('QUICKSTART.md', 'Quick start'))
    checks.append(check_file_exists('.env.example', 'Environment template'))
    print()
    
    # Environment configuration
    print("⚙️ Environment Configuration:")
    checks.append(check_env_example())
    print()
    
    # Summary
    print("=" * 60)
    total = len(checks)
    passed = sum(checks)
    
    if passed == total:
        print(f"✅ All checks passed! ({passed}/{total})")
        print()
        print("🚀 Ready for deployment to Railway!")
        print()
        print("Next steps:")
        print("1. Review DEPLOYMENT_CHECKLIST.md")
        print("2. Push to GitHub")
        print("3. Deploy to Railway")
        print("4. Set environment variables")
        return 0
    else:
        print(f"⚠️ Some checks failed ({passed}/{total} passed)")
        print()
        print("Please fix the issues above before deploying.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
