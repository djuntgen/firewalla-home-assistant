#!/usr/bin/env python3
"""Test runner script for Firewalla integration tests."""
import subprocess
import sys
import os
from pathlib import Path


def run_tests():
    """Run all tests for the Firewalla integration."""
    # Change to the project root directory
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    print("🧪 Running Firewalla Integration Tests")
    print("=" * 50)
    
    # Check if pytest is available
    try:
        import pytest
        print(f"✅ pytest version: {pytest.__version__}")
    except ImportError:
        print("❌ pytest not found. Installing test requirements...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "tests/requirements.txt"], check=True)
    
    # Run tests with coverage if available
    test_cmd = [sys.executable, "-m", "pytest"]
    
    # Add coverage if available
    try:
        import coverage
        test_cmd.extend(["--cov=custom_components.firewalla", "--cov-report=term-missing", "--cov-report=html"])
        print(f"✅ coverage version: {coverage.__version__}")
    except ImportError:
        print("ℹ️  coverage not available (optional)")
    
    # Add test arguments
    test_cmd.extend([
        "tests/",
        "-v",
        "--tb=short",
        "--strict-markers",
        "--disable-warnings"
    ])
    
    print(f"\n🚀 Running command: {' '.join(test_cmd)}")
    print("-" * 50)
    
    # Run the tests
    try:
        result = subprocess.run(test_cmd, check=False)
        
        if result.returncode == 0:
            print("\n" + "=" * 50)
            print("✅ All tests passed!")
            
            # Show coverage report location if available
            coverage_html = project_root / "htmlcov" / "index.html"
            if coverage_html.exists():
                print(f"📊 Coverage report: {coverage_html}")
        else:
            print("\n" + "=" * 50)
            print("❌ Some tests failed!")
            
        return result.returncode
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Error running tests: {e}")
        return 1


def run_specific_test(test_pattern):
    """Run specific tests matching the pattern."""
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    test_cmd = [
        sys.executable, "-m", "pytest",
        "-v",
        "--tb=short",
        "-k", test_pattern
    ]
    
    print(f"🧪 Running tests matching: {test_pattern}")
    print(f"🚀 Command: {' '.join(test_cmd)}")
    print("-" * 50)
    
    result = subprocess.run(test_cmd, check=False)
    return result.returncode


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        # Run specific test pattern
        test_pattern = sys.argv[1]
        return run_specific_test(test_pattern)
    else:
        # Run all tests
        return run_tests()


if __name__ == "__main__":
    sys.exit(main())