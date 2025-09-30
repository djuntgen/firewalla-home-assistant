#!/usr/bin/env python3
"""Validate test structure and imports."""
import sys
import ast
from pathlib import Path


def validate_test_file(test_file):
    """Validate a test file for basic structure."""
    print(f"📁 Validating {test_file.name}...")
    
    try:
        with open(test_file, 'r') as f:
            content = f.read()
        
        # Parse the AST to check for syntax errors
        tree = ast.parse(content)
        
        # Count test functions
        test_functions = []
        test_classes = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                test_functions.append(node.name)
            elif isinstance(node, ast.ClassDef) and node.name.startswith('Test'):
                test_classes.append(node.name)
        
        print(f"  ✅ Syntax valid")
        print(f"  📊 {len(test_classes)} test classes")
        print(f"  🧪 {len(test_functions)} test functions")
        
        if test_classes:
            print(f"  📋 Classes: {', '.join(test_classes[:3])}{'...' if len(test_classes) > 3 else ''}")
        
        return True, len(test_functions)
        
    except SyntaxError as e:
        print(f"  ❌ Syntax error: {e}")
        return False, 0
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False, 0


def main():
    """Main validation function."""
    print("🔍 Validating Firewalla Integration Test Suite")
    print("=" * 50)
    
    test_dir = Path("tests")
    if not test_dir.exists():
        print("❌ Tests directory not found!")
        return 1
    
    test_files = list(test_dir.glob("test_*.py"))
    if not test_files:
        print("❌ No test files found!")
        return 1
    
    total_tests = 0
    valid_files = 0
    
    for test_file in sorted(test_files):
        is_valid, test_count = validate_test_file(test_file)
        if is_valid:
            valid_files += 1
            total_tests += test_count
        print()
    
    # Validate conftest.py
    conftest = test_dir / "conftest.py"
    if conftest.exists():
        print("📁 Validating conftest.py...")
        try:
            with open(conftest, 'r') as f:
                content = f.read()
            ast.parse(content)
            print("  ✅ Conftest syntax valid")
        except Exception as e:
            print(f"  ❌ Conftest error: {e}")
    
    print("=" * 50)
    print(f"📊 Summary:")
    print(f"  ✅ Valid test files: {valid_files}/{len(test_files)}")
    print(f"  🧪 Total test functions: {total_tests}")
    
    # Check for required test files
    required_files = [
        "test_coordinator.py",
        "test_config_flow.py", 
        "test_switch.py",
        "test_sensor.py",
        "test_init.py",
        "test_error_handling.py"
    ]
    
    missing_files = []
    for required in required_files:
        if not (test_dir / required).exists():
            missing_files.append(required)
    
    if missing_files:
        print(f"  ⚠️  Missing files: {', '.join(missing_files)}")
    else:
        print("  ✅ All required test files present")
    
    # Validate imports in a test file
    print("\n🔍 Checking imports in test_coordinator.py...")
    try:
        coordinator_test = test_dir / "test_coordinator.py"
        if coordinator_test.exists():
            with open(coordinator_test, 'r') as f:
                content = f.read()
            
            # Check for key imports
            required_imports = [
                "pytest",
                "AsyncMock",
                "aiohttp",
                "FirewallaMSPClient",
                "FirewallaDataUpdateCoordinator"
            ]
            
            for imp in required_imports:
                if imp in content:
                    print(f"  ✅ {imp} imported")
                else:
                    print(f"  ⚠️  {imp} not found in imports")
    except Exception as e:
        print(f"  ❌ Error checking imports: {e}")
    
    if valid_files == len(test_files) and not missing_files:
        print("\n🎉 Test suite validation successful!")
        return 0
    else:
        print("\n⚠️  Test suite has issues that should be addressed")
        return 1


if __name__ == "__main__":
    sys.exit(main())