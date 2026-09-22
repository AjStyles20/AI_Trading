import subprocess
import os
import sys

def run_tests():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(root_dir, "backend")
    frontend_dir = os.path.join(root_dir, "frontend")

    print("\n" + "="*50)
    print("STARTING OVERALL TEST RUN")
    print("="*50 + "\n")

    # 1. Backend Tests
    print("Running Backend Tests (pytest)...")
    try:
        backend_result = subprocess.run(
            ["pytest", "tests/"], 
            cwd=backend_dir, 
            capture_output=True, 
            text=True
        )
        if backend_result.returncode == 0:
            print("SUCCESS: Backend Tests PASSED!")
            print(backend_result.stdout.strip().split('\n')[-1]) # Print the summary line
        else:
            print("ERROR: Backend Tests FAILED!")
            print(backend_result.stdout)
            print(backend_result.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to execute backend tests: {e}")
        sys.exit(1)

    print("\n" + "-"*50 + "\n")

    # 2. Frontend Tests
    print("Running Frontend Tests (vitest)...")
    try:
        # Use shell=True for npm on Windows
        frontend_result = subprocess.run(
            ["npm", "run", "test"], 
            cwd=frontend_dir, 
            capture_output=True, 
            text=True,
            shell=True
        )
        if frontend_result.returncode == 0:
            print("SUCCESS: Frontend Tests PASSED!")
            # Vitest output may have ANSI codes, but we'll print the last few lines safely
            lines = [line for line in frontend_result.stdout.split('\n') if line.strip()]
            print("\n".join(lines[-3:]))
        else:
            print("ERROR: Frontend Tests FAILED!")
            print(frontend_result.stdout)
            print(frontend_result.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to execute frontend tests: {e}")
        sys.exit(1)

    print("\n" + "="*50)
    print("ALL SYSTEMS GREEN. OVERALL TEST RUN SUCCESSFUL!")
    print("="*50 + "\n")

if __name__ == "__main__":
    run_tests()
