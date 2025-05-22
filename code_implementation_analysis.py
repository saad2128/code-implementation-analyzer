import json
import argparse
import subprocess
import shutil
import os
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional

class CodeImplementationAnalysis:
    """Main class for code implementation analysis workflow."""
    
    def __init__(self, json_file: str, base_dir: str = "code-evaluation"):
        """Initialize the analysis environment.
        
        Args:
            json_file: Path to the JSON file containing task metadata
            base_dir: Base directory for the analysis
        """
        self.json_file = json_file
        self.base_dir = Path(base_dir)
        
        # Load data from JSON file
        with open(json_file, 'r') as f:
            self.data = json.load(f)
        
        # Set up directory structure
        self.dirs = {
            'base': self.base_dir,
            'original': self.base_dir / 'original',
            'implementations': self.base_dir / 'implementations',
            'analysis': self.base_dir / 'analysis',
            'patches': self.base_dir / 'patches',
            'tests': self.base_dir / 'tests',
        }
        
        # Validate required fields
        self._validate_data()
    
    def _validate_data(self):
        """Validate that the JSON data contains all required fields."""
        required_fields = [
            'repo_name', 'before_sha', 'after_sha', 'pr_description',
            'reference_implementation_diff'
        ]
        
        missing_fields = [field for field in required_fields if field not in self.data]
        if missing_fields:
            print(f"❌ Error: Missing required fields in JSON data: {', '.join(missing_fields)}")
            sys.exit(1)
    
    def setup_environment(self):
        """Create the directory structure for analysis."""
        for dir_path in self.dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)

        # Create metadata file
        with open(self.dirs['base'] / 'metadata.json', 'w') as f:
            json.dump({
                'repo_name': self.data['repo_name'],
                'before_sha': self.data['before_sha'],
                'after_sha': self.data['after_sha'],
                'pr_description': self.data['pr_description'],
                'setup_time': time.strftime("%Y-%m-%d %H:%M:%S"),
            }, f, indent=2)

        # Create task description file
        with open(self.dirs['base'] / 'task.md', 'w') as f:
            f.write(f"# Task Description\n\n{self.data['pr_description']}")
        
        # Create README file
        self._create_readme()
        
        print("✅ Environment setup complete.")
    
    def _create_readme(self):
        """Create a README file for the project."""
        readme_content = f"""# Code Implementation Analysis

## Task Overview

Repository: {self.data['repo_name']}
Before SHA: {self.data['before_sha']}
After SHA: {self.data['after_sha']}

## Directory Structure

- `original/`: Original repository checked out at the 'before' state
- `implementations/`: Contains each implementation variant
- `patches/`: Contains patch files for each implementation
- `analysis/`: Place to store your analysis documents
- `tests/`: Any test results or test-related files

## Analysis Workflow

1. Understand the task by reading `task.md`
2. Examine original code in `original/` directory
3. Review each implementation in `implementations/` directory
4. Compare implementations using criteria in guidelines
5. Document your analysis in `analysis/` directory
6. Identify the best implementation and provide detailed rationale

## Criteria for Evaluation

- Code Quality (clarity, simplicity, consistency, documentation)
- Architecture & Design (modularity, cohesion, coupling, extensibility)
- Development Process (incremental approach, reviewability, testing)
- Risk & Maintainability (error handling, edge cases, future maintenance)
- Performance & Efficiency (resource usage, algorithmic efficiency, scalability)

## Scripts

- `run_analysis.py`: Main script to run the complete analysis workflow
- `compare_implementations.py`: Helper script to compare implementations
- `validate_implementations.py`: Validate the implementations against tests
"""
        with open(self.dirs['base'] / 'README.md', 'w') as f:
            f.write(readme_content)
    
    def extract_diffs(self):
        """Extract diff files from JSON data."""
        # Extract reference implementation diff
        with open(self.dirs['patches'] / 'reference_implementation.patch', 'w') as f:
            f.write(self.data['reference_implementation_diff'])

        # Extract implementation diffs
        extracted_count = 0
        for i in range(1, 5):
            diff_key = f'diff_{i}'
            if diff_key in self.data and self.data[diff_key]:
                with open(self.dirs['patches'] / f'implementation_{i}.patch', 'w') as f:
                    f.write(self.data[diff_key])
                extracted_count += 1
        
        print(f"✅ Extracted {extracted_count} implementation diffs and reference implementation.")
    
    def detect_default_branch(self, repo_name):
        """Detect the default branch (main or master) from remote.
        
        Args:
            repo_name: GitHub repository name in format 'username/repo'
            
        Returns:
            The default branch name
        """
        import urllib.request
        import re

        # GitHub redirects HEAD to the default branch
        url = f"https://github.com/{repo_name}"
        try:
            with urllib.request.urlopen(url) as response:
                html = response.read().decode()
                match = re.search(r'branch=([a-zA-Z0-9_\-]+)"', html)
                if match:
                    return match.group(1)
        except Exception as e:
            print(f"⚠️ Warning: Could not detect default branch: {str(e)}")
        
        return 'main'  # fallback
    
    def clone_repository(self):
        """Clone the repository and checkout the correct SHA."""
        target_dir = self.dirs['original']
        repo_name = self.data['repo_name']
        before_sha = self.data['before_sha']
        
        # If directory exists but is empty, delete and re-clone
        if target_dir.exists() and not any(target_dir.iterdir()):
            print("⚠️ Original repo directory exists but is empty. Re-cloning...")
            shutil.rmtree(target_dir)

        if not target_dir.exists():
            repo_url = f'https://github.com/{repo_name}.git'
            print(f"📥 Cloning from {repo_url}")
            try:
                subprocess.run(['git', 'clone', repo_url, str(target_dir)], check=True)
            except subprocess.CalledProcessError:
                print(f"❌ Failed to clone repository {repo_url}")
                sys.exit(1)

            # Determine actual branch or SHA
            actual_sha = before_sha
            if before_sha in ('main', 'master'):
                default_branch = self.detect_default_branch(repo_name)
                print(f"🔍 Detected default branch: {default_branch}")
                actual_sha = default_branch

            try:
                subprocess.run(['git', '-C', str(target_dir), 'checkout', actual_sha], check=True)
                print(f"✅ Repository checked out to {actual_sha}.")
            except subprocess.CalledProcessError:
                print(f"❌ Failed to checkout {actual_sha}")
                sys.exit(1)
        else:
            print("ℹ️ Repository already exists and is non-empty. Skipping clone.")
    
    def handle_remove_readonly(self, func, path, exc):
        """Handle read-only files when removing directories."""
        import stat
        os.chmod(path, stat.S_IWRITE)
        func(path)
    
    def _apply_patch_manually(self, patch_path: Path, target_dir: Path) -> bool:
        """Manually apply a patch by parsing it and applying changes.
        
        Args:
            patch_path: Path to the patch file
            target_dir: Directory to apply the patch to
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(patch_path, 'r', encoding='utf-8') as f:
                patch_content = f.read()
            
            # Simple patch parser for basic unified diff format
            lines = patch_content.split('\n')
            current_file = None
            file_changes = {}
            is_new_file = False
            is_binary = False
            
            i = 0
            while i < len(lines):
                line = lines[i]
                
                # Look for file headers
                if line.startswith('diff --git'):
                    # Extract filename from "diff --git a/path b/path"
                    parts = line.split()
                    if len(parts) >= 4:
                        current_file = parts[3][2:]  # Remove "b/" prefix
                        file_changes[current_file] = {
                            'hunks': [],
                            'is_new_file': False,
                            'is_binary': False
                        }
                        is_new_file = False
                        is_binary = False
                elif line.startswith('new file mode'):
                    # This is a new file
                    if current_file:
                        file_changes[current_file]['is_new_file'] = True
                        is_new_file = True
                elif line.startswith('index') and current_file:
                    # Check if it's a binary file (contains non-text characters indicator)
                    if '...' in line and ('GIT binary patch' in patch_content or 'Binary files' in patch_content):
                        file_changes[current_file]['is_binary'] = True
                        is_binary = True
                elif line.startswith('@@') and current_file and not is_binary:
                    # Parse hunk header to get line numbers
                    # Format: @@ -old_start,old_count +new_start,new_count @@
                    hunk_match = line.split()
                    if len(hunk_match) >= 3:
                        old_info = hunk_match[1][1:]  # Remove '-'
                        new_info = hunk_match[2][1:]  # Remove '+'
                        
                        old_start = int(old_info.split(',')[0]) if ',' in old_info else int(old_info)
                        new_start = int(new_info.split(',')[0]) if ',' in new_info else int(new_info)
                        
                        # Collect hunk content
                        i += 1
                        hunk_lines = []
                        while i < len(lines) and not lines[i].startswith('@@') and not lines[i].startswith('diff --git'):
                            if lines[i].startswith(('+', '-', ' ')) or lines[i] == '':
                                hunk_lines.append(lines[i])
                            elif lines[i].startswith('\\'):
                                # Handle "\ No newline at end of file"
                                hunk_lines.append(lines[i])
                            i += 1
                        i -= 1  # Back up one since the outer loop will increment
                        
                        file_changes[current_file]['hunks'].append({
                            'old_start': old_start,
                            'new_start': new_start,
                            'lines': hunk_lines
                        })
                
                i += 1
            
            # Apply changes to files
            for file_path, file_info in file_changes.items():
                full_file_path = target_dir / file_path
                
                # Handle new files
                if file_info['is_new_file']:
                    if file_info['is_binary']:
                        print(f"⚠️ Skipping binary file: {file_path}")
                        continue
                    
                    # Create directory if it doesn't exist
                    full_file_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Create new file from patch content
                    new_content = []
                    for hunk in file_info['hunks']:
                        for hunk_line in hunk['lines']:
                            if hunk_line.startswith('+'):
                                new_content.append(hunk_line[1:])
                            elif hunk_line.startswith('\\'):
                                # Handle "\ No newline at end of file"
                                if 'No newline at end of file' in hunk_line:
                                    # Remove the last newline if it exists
                                    if new_content and new_content[-1].endswith('\n'):
                                        new_content[-1] = new_content[-1][:-1]
                    
                    # Write new file
                    with open(full_file_path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(new_content))
                        if new_content and not new_content[-1].endswith('\n'):
                            f.write('\n')
                    
                    print(f"✅ Created new file: {file_path}")
                    
                else:
                    # Handle existing file modifications
                    if not full_file_path.exists():
                        print(f"⚠️ File not found for modification: {full_file_path}")
                        continue
                    
                    # Read original file
                    with open(full_file_path, 'r', encoding='utf-8') as f:
                        original_lines = f.readlines()
                    
                    # Apply hunks (simple implementation - works for basic cases)
                    modified_lines = original_lines.copy()
                    
                    for hunk in file_info['hunks']:
                        # Simple approach: find the context and apply changes
                        hunk_lines = hunk['lines']
                        
                        # Extract additions and removals
                        additions = []
                        removals = []
                        
                        for hunk_line in hunk_lines:
                            if hunk_line.startswith('+'):
                                additions.append(hunk_line[1:] + '\n')
                            elif hunk_line.startswith('-'):
                                removals.append(hunk_line[1:] + '\n')
                        
                        # For simple patches, we'll do a basic find-and-replace
                        if removals and additions:
                            # Find the lines to remove in the file
                            for i, line in enumerate(modified_lines):
                                if i <= len(modified_lines) - len(removals):
                                    if modified_lines[i:i+len(removals)] == removals:
                                        # Replace the removed lines with added lines
                                        modified_lines[i:i+len(removals)] = additions
                                        break
                        elif additions and not removals:
                            # Pure addition - add at the appropriate location
                            start_line = hunk['old_start'] - 1
                            if 0 <= start_line <= len(modified_lines):
                                modified_lines[start_line:start_line] = additions
                        elif removals and not additions:
                            # Pure removal
                            for i, line in enumerate(modified_lines):
                                if i <= len(modified_lines) - len(removals):
                                    if modified_lines[i:i+len(removals)] == removals:
                                        del modified_lines[i:i+len(removals)]
                                        break
                    
                    # Write modified file
                    with open(full_file_path, 'w', encoding='utf-8') as f:
                        f.writelines(modified_lines)
                    
                    print(f"✅ Modified existing file: {file_path}")
            
            return True
            
        except Exception as e:
            print(f"❌ Manual patch application failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def apply_patches(self):
        """Apply patches to create implementation directories."""
        implementations_applied = 0
        
        for i in range(1, 5):
            patch_path = self.dirs['patches'] / f'implementation_{i}.patch'
            impl_dir = self.dirs['implementations'] / f'impl_{i}'
            
            if patch_path.exists():
                print(f"📝 Processing implementation {i}...")
                
                # Remove existing implementation directory if it exists
                if impl_dir.exists():
                    shutil.rmtree(impl_dir, onerror=self.handle_remove_readonly)
                
                # Copy original repository
                shutil.copytree(self.dirs['original'], impl_dir)
                
                # Initialize git in the implementation directory
                subprocess.run(['git', '-C', str(impl_dir), 'init'], check=True)
                subprocess.run(['git', '-C', str(impl_dir), 'add', '.'], check=True)
                
                # Create initial commit
                result = subprocess.run(['git', '-C', str(impl_dir), 'diff', '--cached', '--quiet'])
                if result.returncode != 0:
                    subprocess.run(['git', '-C', str(impl_dir), 'commit', '-m', 'Initial commit'], check=True)
                else:
                    print(f"⚠️ Nothing to commit in {impl_dir}, skipping initial commit.")
                
                # Create implementation branch
                impl_name = f'impl_{i}'
                subprocess.run(['git', '-C', str(impl_dir), 'checkout', '-b', impl_name], check=True)
                
                # Apply patch - Use absolute path to ensure correct path resolution
                absolute_patch_path = patch_path.resolve()
                
                try:
                    # Try git apply with whitespace fixes
                    result = subprocess.run(['git', '-C', str(impl_dir), 'apply', '--whitespace=fix', str(absolute_patch_path)], 
                                          capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        print(f"⚠️ Git apply failed for {impl_name}, trying with ignore whitespace...")
                        print(f"Git apply error: {result.stderr}")
                        
                        # Try git apply with ignore whitespace
                        result = subprocess.run(['git', '-C', str(impl_dir), 'apply', '--ignore-whitespace', str(absolute_patch_path)], 
                                              capture_output=True, text=True)
                        
                        if result.returncode != 0:
                            print(f"⚠️ Git apply still failed, trying manual application...")
                            # Try manual patch application
                            success = self._apply_patch_manually(absolute_patch_path, impl_dir)
                            if not success:
                                print(f"❌ Manual patch application failed for {impl_name}")
                                continue
                    
                    # Stage and commit changes
                    subprocess.run(['git', '-C', str(impl_dir), 'add', '.'], check=True)
                    
                    # Check if there are any changes to commit
                    result = subprocess.run(['git', '-C', str(impl_dir), 'diff', '--cached', '--quiet'])
                    if result.returncode != 0:
                        subprocess.run(['git', '-C', str(impl_dir), 'commit', '-m', f'Apply {impl_name}'], check=True)
                        print(f"✅ Patch applied for {impl_name}.")
                        implementations_applied += 1
                    else:
                        print(f"⚠️ No changes to commit for {impl_name} after applying patch.")
                        
                except subprocess.CalledProcessError as e:
                    print(f"❌ Failed to apply patch for {impl_name}: {e}")
            else:
                print(f"⚠️ Patch file not found for implementation {i}: {patch_path}")
        
        print(f"✅ Applied patches for {implementations_applied} implementations.")
    
    def create_analysis_template(self):
        """Create an analysis template file."""
        template_content = """# Implementation Analysis

## Task Overview

[Brief description of the task and requirements]

## Implementation Comparison

### Implementation 1

**Strategy:**
[Describe the approach taken]

**Strengths:**
- [Strength 1]
- [Strength 2]

**Weaknesses:**
- [Weakness 1]
- [Weakness 2]

### Implementation 2

**Strategy:**
[Describe the approach taken]

**Strengths:**
- [Strength 1]
- [Strength 2]

**Weaknesses:**
- [Weakness 1]
- [Weakness 2]

### Implementation 3

**Strategy:**
[Describe the approach taken]

**Strengths:**
- [Strength 1]
- [Strength 2]

**Weaknesses:**
- [Weakness 1]
- [Weakness 2]

### Implementation 4

**Strategy:**
[Describe the approach taken]

**Strengths:**
- [Strength 1]
- [Strength 2]

**Weaknesses:**
- [Weakness 1]
- [Weakness 2]

## Evaluation Matrix

| Criteria | Impl 1 | Impl 2 | Impl 3 | Impl 4 |
|----------|--------|--------|--------|--------|
| Code Quality | | | | |
| Architecture | | | | |
| Development Process | | | | |
| Risk & Maintainability | | | | |
| Performance | | | | |

## Best Implementation

Implementation: [Number]

**Rationale:**
[Detailed explanation of why this implementation is best]

## Potential Improvements

[Suggestions for improving the chosen implementation]
"""
        with open(self.dirs['analysis'] / 'analysis_template.md', 'w') as f:
            f.write(template_content)
        
        print("✅ Created analysis template file.")
    
    def summarize_implementations(self):
        """Create a summary of the implementations."""
        summary = {
            "task": self.data['pr_description'][:100] + "..." if len(self.data['pr_description']) > 100 else self.data['pr_description'],
            "repo": self.data['repo_name'],
            "implementations": []
        }
        
        for i in range(1, 5):
            patch_path = self.dirs['patches'] / f'implementation_{i}.patch'
            if patch_path.exists():
                # Count lines in patch
                with open(patch_path, 'r') as f:
                    patch_content = f.read()
                    lines = patch_content.count('\n')
                    
                # Count files modified in patch
                files_modified = patch_content.count('diff --git')
                
                summary["implementations"].append({
                    "number": i,
                    "files_modified": files_modified,
                    "patch_lines": lines
                })
        
        with open(self.dirs['base'] / 'implementation_summary.json', 'w') as f:
            json.dump(summary, f, indent=2)
        
        print("✅ Created implementation summary.")
    
    def run_all(self):
        """Run the complete analysis workflow."""
        self.setup_environment()
        self.extract_diffs()
        self.clone_repository()
        self.apply_patches()
        self.create_analysis_template()
        self.summarize_implementations()
        
        print("\n🎉 Setup complete! You can now start analyzing the implementations.")
        print(f"📁 Project directory: {self.dirs['base']}")
        print(f"📝 Analysis template: {self.dirs['analysis'] / 'analysis_template.md'}")
        print("\nNext steps:")
        print("1. Review the task description in task.md")
        print("2. Examine each implementation in the implementations/ directory")
        print("3. Fill out the analysis template in the analysis/ directory")
        print("4. Identify the best implementation and provide detailed rationale")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Code Implementation Analysis Workflow")
    parser.add_argument("json_file", help="Path to JSON file containing task metadata")
    parser.add_argument("--dir", default="code-evaluation", help="Base directory for analysis")
    parser.add_argument("--step", choices=["setup", "extract", "clone", "patch", "template", "summary", "all"], 
                      default="all", help="Specific step to run")
    
    args = parser.parse_args()
    
    analysis = CodeImplementationAnalysis(args.json_file, args.dir)
    
    if args.step == "setup":
        analysis.setup_environment()
    elif args.step == "extract":
        analysis.extract_diffs()
    elif args.step == "clone":
        analysis.clone_repository()
    elif args.step == "patch":
        analysis.apply_patches()
    elif args.step == "template":
        analysis.create_analysis_template()
    elif args.step == "summary":
        analysis.summarize_implementations()
    else:  # all
        analysis.run_all()


if __name__ == "__main__":
    main()