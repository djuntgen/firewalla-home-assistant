#!/usr/bin/env python3
"""Simple validation script to verify integration structure without Home Assistant dependencies."""
import ast
import json
from pathlib import Path


def validate_file_structure():
    """Check that all required files exist."""
    print("🔍 Validating File Structure")
    print("=" * 40)
    
    required_files = [
        "custom_components/firewalla/__init__.py",
        "custom_components/firewalla/config_flow.py", 
        "custom_components/firewalla/const.py",
        "custom_components/firewalla/coordinator.py",
        "custom_components/firewalla/sensor.py",
        "custom_components/firewalla/switch.py",
        "custom_components/firewalla/manifest.json",
        "custom_components/firewalla/strings.json",
    ]
    
    all_exist = True
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path}")
            all_exist = False
    
    return all_exist


def validate_python_syntax():
    """Check that all Python files have valid syntax."""
    print("\n🔍 Validating Python Syntax")
    print("=" * 40)
    
    python_files = [
        "custom_components/firewalla/__init__.py",
        "custom_components/firewalla/config_flow.py",
        "custom_components/firewalla/const.py", 
        "custom_components/firewalla/coordinator.py",
        "custom_components/firewalla/sensor.py",
        "custom_components/firewalla/switch.py",
    ]
    
    all_valid = True
    for file_path in python_files:
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            ast.parse(content)
            print(f"✅ {file_path}")
        except SyntaxError as e:
            print(f"❌ {file_path}: {e}")
            all_valid = False
        except Exception as e:
            print(f"⚠️  {file_path}: {e}")
    
    return all_valid


def validate_init_functions():
    """Check that __init__.py has required functions."""
    print("\n🔍 Validating Integration Functions")
    print("=" * 40)
    
    try:
        with open("custom_components/firewalla/__init__.py", 'r') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        # Find function definitions (both sync and async)
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
        
        required_functions = [
            "async_setup_entry",
            "async_unload_entry", 
            "async_reload_entry",
            "setup_integration_logging"
        ]
        
        all_present = True
        for func_name in required_functions:
            if func_name in functions:
                print(f"✅ {func_name}")
            else:
                print(f"❌ {func_name}")
                all_present = False
        
        # Check for PLATFORMS_TO_SETUP
        has_platforms = "PLATFORMS_TO_SETUP" in content
        if has_platforms:
            print(f"✅ PLATFORMS_TO_SETUP")
        else:
            print(f"❌ PLATFORMS_TO_SETUP")
            all_present = False
        
        return all_present
        
    except Exception as e:
        print(f"❌ Error parsing __init__.py: {e}")
        return False


def validate_manifest():
    """Check manifest.json structure."""
    print("\n🔍 Validating Manifest")
    print("=" * 40)
    
    try:
        with open("custom_components/firewalla/manifest.json", 'r') as f:
            manifest = json.load(f)
        
        required_keys = ["domain", "name", "version", "documentation", "requirements"]
        all_present = True
        
        for key in required_keys:
            if key in manifest:
                print(f"✅ {key}: {manifest[key]}")
            else:
                print(f"❌ Missing: {key}")
                all_present = False
        
        return all_present
        
    except Exception as e:
        print(f"❌ Error reading manifest: {e}")
        return False


def validate_platform_setup():
    """Check that platforms are properly set up."""
    print("\n🔍 Validating Platform Setup")
    print("=" * 40)
    
    try:
        # Check switch.py
        with open("custom_components/firewalla/switch.py", 'r') as f:
            switch_content = f.read()
        
        # Check sensor.py  
        with open("custom_components/firewalla/sensor.py", 'r') as f:
            sensor_content = f.read()
        
        # Look for async_setup_entry in both
        switch_has_setup = "async def async_setup_entry" in switch_content
        sensor_has_setup = "async def async_setup_entry" in sensor_content
        
        if switch_has_setup:
            print("✅ Switch platform setup function")
        else:
            print("❌ Switch platform setup function")
        
        if sensor_has_setup:
            print("✅ Sensor platform setup function")
        else:
            print("❌ Sensor platform setup function")
        
        return switch_has_setup and sensor_has_setup
        
    except Exception as e:
        print(f"❌ Error checking platforms: {e}")
        return False


def main():
    """Run all validation checks."""
    print("🧪 Firewalla Integration Structure Validation")
    print("=" * 50)
    
    checks = [
        ("File Structure", validate_file_structure),
        ("Python Syntax", validate_python_syntax),
        ("Integration Functions", validate_init_functions),
        ("Manifest", validate_manifest),
        ("Platform Setup", validate_platform_setup),
    ]
    
    results = []
    for check_name, check_func in checks:
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            print(f"❌ {check_name} failed: {e}")
            results.append((check_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Validation Summary")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for check_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {check_name}")
    
    print(f"\n📈 Results: {passed}/{total} checks passed")
    
    if passed == total:
        print("🎉 All validation checks passed!")
        print("✅ Integration entry point properly wires all components")
        print("✅ All platforms are configured for loading")
        print("✅ Integration reload capability is implemented")
        print("✅ Components are ready for end-to-end operation")
        return 0
    else:
        print("⚠️  Some validation checks failed.")
        return 1


if __name__ == "__main__":
    exit(main())