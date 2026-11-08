#!/usr/bin/env python3
"""Validation script to verify Firewalla integration components work together."""
import sys
import importlib.util
from pathlib import Path


def validate_integration_structure():
    """Validate that all integration files exist and can be imported."""
    print("🔍 Validating Firewalla Integration Structure")
    print("=" * 50)
    
    # Check required files exist
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
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
        else:
            print(f"✅ {file_path}")
    
    if missing_files:
        print(f"\n❌ Missing files:")
        for file_path in missing_files:
            print(f"   - {file_path}")
        return False
    
    print(f"\n✅ All required files present")
    return True


def validate_imports():
    """Validate that integration modules can be imported."""
    print("\n🔍 Validating Module Imports")
    print("=" * 50)
    
    modules_to_test = [
        ("custom_components.firewalla.const", "Constants"),
        ("custom_components.firewalla.coordinator", "Coordinator"),
        ("custom_components.firewalla.config_flow", "Config Flow"),
        ("custom_components.firewalla.sensor", "Sensor Platform"),
        ("custom_components.firewalla.switch", "Switch Platform"),
        ("custom_components.firewalla", "Main Integration"),
    ]
    
    failed_imports = []
    
    for module_name, description in modules_to_test:
        try:
            # Add the project root to sys.path
            project_root = Path(__file__).parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            spec = importlib.util.spec_from_file_location(
                module_name, 
                str(project_root / (module_name.replace(".", "/") + ".py"))
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                print(f"✅ {description}: {module_name}")
            else:
                failed_imports.append((module_name, description, "Could not create spec"))
        except Exception as e:
            failed_imports.append((module_name, description, str(e)))
    
    if failed_imports:
        print(f"\n❌ Failed imports:")
        for module_name, description, error in failed_imports:
            print(f"   - {description} ({module_name}): {error}")
        return False
    
    print(f"\n✅ All modules can be imported")
    return True


def validate_integration_functions():
    """Validate that key integration functions are defined."""
    print("\n🔍 Validating Integration Functions")
    print("=" * 50)
    
    try:
        # Add the project root to sys.path
        project_root = Path(__file__).parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        # Import the main integration module
        spec = importlib.util.spec_from_file_location(
            "custom_components.firewalla", 
            str(project_root / "custom_components/firewalla/__init__.py")
        )
        if not spec or not spec.loader:
            print("❌ Could not load main integration module")
            return False
        
        integration_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(integration_module)
        
        # Check required functions
        required_functions = [
            "async_setup_entry",
            "async_unload_entry", 
            "async_reload_entry",
        ]
        
        missing_functions = []
        for func_name in required_functions:
            if hasattr(integration_module, func_name):
                print(f"✅ {func_name}")
            else:
                missing_functions.append(func_name)
        
        if missing_functions:
            print(f"\n❌ Missing functions:")
            for func_name in missing_functions:
                print(f"   - {func_name}")
            return False
        
        # Check that PLATFORMS_TO_SETUP is defined
        if hasattr(integration_module, "PLATFORMS_TO_SETUP"):
            platforms = integration_module.PLATFORMS_TO_SETUP
            print(f"✅ PLATFORMS_TO_SETUP: {platforms}")
            
            # Verify expected platforms
            from homeassistant.const import Platform
            expected_platforms = [Platform.SWITCH, Platform.SENSOR]
            if set(platforms) == set(expected_platforms):
                print(f"✅ Correct platforms configured")
            else:
                print(f"⚠️  Platform mismatch. Expected: {expected_platforms}, Got: {platforms}")
        else:
            print(f"❌ PLATFORMS_TO_SETUP not defined")
            return False
        
        print(f"\n✅ All integration functions present")
        return True
        
    except Exception as e:
        print(f"❌ Error validating integration functions: {e}")
        return False


def validate_manifest():
    """Validate manifest.json structure."""
    print("\n🔍 Validating Manifest")
    print("=" * 50)
    
    try:
        import json
        
        manifest_path = Path("custom_components/firewalla/manifest.json")
        if not manifest_path.exists():
            print("❌ manifest.json not found")
            return False
        
        with open(manifest_path) as f:
            manifest = json.load(f)
        
        required_keys = ["domain", "name", "version", "documentation", "requirements", "codeowners"]
        missing_keys = []
        
        for key in required_keys:
            if key in manifest:
                print(f"✅ {key}: {manifest[key]}")
            else:
                missing_keys.append(key)
        
        if missing_keys:
            print(f"\n❌ Missing manifest keys:")
            for key in missing_keys:
                print(f"   - {key}")
            return False
        
        print(f"\n✅ Manifest structure valid")
        return True
        
    except Exception as e:
        print(f"❌ Error validating manifest: {e}")
        return False


def main():
    """Run all validation checks."""
    print("🧪 Firewalla Integration Validation")
    print("=" * 60)
    
    checks = [
        ("File Structure", validate_integration_structure),
        ("Module Imports", validate_imports),
        ("Integration Functions", validate_integration_functions),
        ("Manifest", validate_manifest),
    ]
    
    results = []
    for check_name, check_func in checks:
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            print(f"❌ {check_name} check failed with error: {e}")
            results.append((check_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Validation Summary")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for check_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {check_name}")
        if result:
            passed += 1
    
    print(f"\n📈 Results: {passed}/{total} checks passed")
    
    if passed == total:
        print("🎉 All validation checks passed! Integration is ready.")
        return 0
    else:
        print("⚠️  Some validation checks failed. Please review the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())