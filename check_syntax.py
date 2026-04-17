#!/usr/bin/env python3
"""
Syntax Checker for Ham Radio App
=================================
Checks all Python files for syntax errors.
"""

import os
import py_compile
import sys

def check_file(filepath):
    """Check a single Python file for syntax errors."""
    try:
        py_compile.compile(filepath, doraise=True)
        return True, None
    except py_compile.PyCompileError as e:
        return False, str(e)

def check_directory(directory):
    """Check all Python files in a directory."""
    errors = []
    
    for root, dirs, files in os.walk(directory):
        # Skip virtual environments and __pycache__
        dirs[:] = [d for d in dirs if d not in ['venv', 'env', '__pycache__', '.git']]
        
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                is_valid, error = check_file(filepath)
                
                if is_valid:
                    print(f"✓ {filepath}")
                else:
                    print(f"✗ {filepath}")
                    print(f"  Error: {error}")
                    errors.append((filepath, error))
    
    return errors

if __name__ == '__main__':
    print("Checking Python syntax...")
    print("=" * 50)
    
    # Check current directory
    errors = check_directory('.')
    
    print("=" * 50)
    if errors:
        print(f"\n{len(errors)} file(s) with syntax errors:")
        for filepath, error in errors:
            print(f"\n{filepath}:")
            print(f"  {error}")
        sys.exit(1)
    else:
        print("\n✓ All Python files have valid syntax!")
        sys.exit(0)
