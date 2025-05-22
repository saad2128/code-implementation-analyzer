import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import difflib
import re
from collections import defaultdict
import tempfile


class ImplementationComparison:
    """Tool for comparing different code implementations."""
    
    def __init__(self, base_dir: str = "code-evaluation"):
        """Initialize the comparison tool.
        
        Args:
            base_dir: Base directory for the analysis
        """
        self.base_dir = Path(base_dir)
        self.metadata_file = self.base_dir / 'metadata.json'
        
        # Verify the project structure
        if not self.metadata_file.exists():
            print(f"❌ Error: Metadata file not found at {self.metadata_file}")
            print("Make sure you run the setup script first.")
            sys.exit(1)
        
        # Load metadata
        with open(self.metadata_file, 'r') as f:
            self.metadata = json.load(f)
        
        # Set up directories
        self.dirs = {
            'base': self.base_dir,
            'original': self.base_dir / 'original',
            'implementations': self.base_dir / 'implementations',
            'analysis': self.base_dir / 'analysis',
            'patches': self.base_dir / 'patches',
        }
    
    def list_implementations(self) -> List[str]:
        """List all available implementations.
        
        Returns:
            List of implementation directory names
        """
        implementations = []
        
        for item in os.listdir(self.dirs['implementations']):
            path = self.dirs['implementations'] / item
            if path.is_dir() and item.startswith('impl_'):
                implementations.append(item)
        
        return sorted(implementations)
    
    def get_modified_files(self, impl_dir: Path) -> List[str]:
        """Get list of files modified in an implementation.
        
        Args:
            impl_dir: Path to implementation directory
            
        Returns:
            List of files that were modified
        """
        modified_files = []
        
        # Method 1: Try using git diff if there are commits
        try:
            # Check if there are commits
            result = subprocess.run(
                ['git', '-C', str(impl_dir), 'log', '--oneline'],
                capture_output=True, text=True, check=True
            )
            
            if result.stdout.strip():
                # Get files modified in the last commit (which should be the implementation)
                result = subprocess.run(
                    ['git', '-C', str(impl_dir), 'diff', '--name-only', 'HEAD~1', 'HEAD'],
                    capture_output=True, text=True, check=True
                )
                git_files = [line.strip() for line in result.stdout.split('\n') if line.strip()]
                
                if git_files:
                    return git_files
        except subprocess.CalledProcessError:
            pass
        
        # Method 2: Fallback to comparing with original directory
        print(f"📁 Comparing {impl_dir.name} with original directory...")
        
        # Get all files in the implementation directory
        for root, _, files in os.walk(impl_dir):
            for file in files:
                file_path = Path(root) / file
                rel_path = file_path.relative_to(impl_dir)
                
                # Skip git files
                if '.git' in rel_path.parts:
                    continue
                
                # Check if file exists in original and is different, or is new
                original_file = self.dirs['original'] / rel_path
                
                if not original_file.exists():
                    # New file
                    modified_files.append(str(rel_path))
                    print(f"  📝 New file: {rel_path}")
                elif self._files_differ(original_file, file_path):
                    # Modified file
                    modified_files.append(str(rel_path))
                    print(f"  🔄 Modified file: {rel_path}")
        
        return sorted(modified_files)
    
    def _files_differ(self, file1: Path, file2: Path) -> bool:
        """Check if two files have different content.
        
        Args:
            file1: First file to compare
            file2: Second file to compare
            
        Returns:
            True if files have different content, False otherwise
        """
        try:
            # First check if files have same size
            if file1.stat().st_size != file2.stat().st_size:
                return True
                
            # Then check content
            with open(file1, 'rb') as f1, open(file2, 'rb') as f2:
                return f1.read() != f2.read()
        except Exception as e:
            print(f"⚠️ Warning: Could not compare {file1} and {file2}: {e}")
            # If we can't read the files, consider them different
            return True
    
    def generate_implementation_report(self, impl_name: str, 
                                       output_file: Optional[Path] = None) -> None:
        """Generate a detailed report for an implementation.
        
        Args:
            impl_name: Name of the implementation (e.g., 'impl_1')
            output_file: Path to save the report (optional)
        """
        impl_dir = self.dirs['implementations'] / impl_name
        if not impl_dir.exists():
            print(f"❌ Error: Implementation directory {impl_name} not found")
            return
        
        modified_files = self.get_modified_files(impl_dir)
        
        # Generate report
        report = [f"# Implementation Report: {impl_name}", ""]
        
        # Summary section
        report.append("## Summary")
        report.append(f"- Implementation: {impl_name}")
        report.append(f"- Files modified: {len(modified_files)}")
        report.append("")
        
        # Modified files section
        report.append("## Modified Files")
        for file in modified_files:
            report.append(f"- {file}")
        report.append("")
        
        # File changes section
        report.append("## File Changes")
        for file in modified_files:
            original_file = self.dirs['original'] / file
            impl_file = impl_dir / file
            
            report.append(f"### {file}")
            
            # Handle new files
            if not original_file.exists():
                report.append("*New file created in this implementation*")
                try:
                    with open(impl_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        # Limit file content display to avoid huge reports
                        if len(content) > 2000:
                            content = content[:2000] + "\n... (truncated)"
                        report.append("```")
                        report.append(content)
                        report.append("```")
                except Exception as e:
                    report.append(f"*Error reading file: {str(e)}*")
            else:
                # Generate diff
                try:
                    with open(original_file, 'r', encoding='utf-8', errors='ignore') as f1, \
                         open(impl_file, 'r', encoding='utf-8', errors='ignore') as f2:
                        original_lines = f1.readlines()
                        impl_lines = f2.readlines()
                        
                        diff = list(difflib.unified_diff(
                            original_lines, impl_lines,
                            fromfile=f"original/{file}",
                            tofile=f"{impl_name}/{file}",
                            lineterm=""
                        ))
                        
                        if diff:
                            report.append("```diff")
                            report.extend(diff)
                            report.append("```")
                        else:
                            report.append("*No changes detected*")
                except Exception as e:
                    report.append(f"*Error generating diff: {str(e)}*")
            
            report.append("")
        
        # Save or print report
        report_text = "\n".join(report)
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_text)
            print(f"✅ Report saved to {output_file}")
        else:
            print(report_text)
    
    def compare_implementations(self, impl1: str, impl2: str, 
                               output_file: Optional[Path] = None) -> None:
        """Compare two implementations and generate a report.
        
        Args:
            impl1: First implementation to compare
            impl2: Second implementation to compare
            output_file: Path to save the report (optional)
        """
        impl1_dir = self.dirs['implementations'] / impl1
        impl2_dir = self.dirs['implementations'] / impl2
        
        if not impl1_dir.exists():
            print(f"❌ Error: Implementation directory {impl1} not found")
            return
        
        if not impl2_dir.exists():
            print(f"❌ Error: Implementation directory {impl2} not found")
            return
        
        print(f"🔍 Analyzing {impl1}...")
        impl1_files = set(self.get_modified_files(impl1_dir))
        print(f"🔍 Analyzing {impl2}...")
        impl2_files = set(self.get_modified_files(impl2_dir))
        
        all_files = sorted(impl1_files.union(impl2_files))
        common_files = sorted(impl1_files.intersection(impl2_files))
        only_impl1 = sorted(impl1_files - impl2_files)
        only_impl2 = sorted(impl2_files - impl1_files)
        
        print(f"📊 Found {len(impl1_files)} files in {impl1}, {len(impl2_files)} files in {impl2}")
        print(f"📊 Common files: {len(common_files)}, Only in {impl1}: {len(only_impl1)}, Only in {impl2}: {len(only_impl2)}")
        
        # Generate report
        report = [f"# Implementation Comparison: {impl1} vs {impl2}", ""]
        
        # Summary section
        report.append("## Summary")
        report.append(f"- First implementation: {impl1}")
        report.append(f"- Second implementation: {impl2}")
        report.append(f"- Total files modified: {len(all_files)}")
        report.append(f"- Files modified in both: {len(common_files)}")
        report.append(f"- Files modified only in {impl1}: {len(only_impl1)}")
        report.append(f"- Files modified only in {impl2}: {len(only_impl2)}")
        report.append("")
        
        # Files overview
        if only_impl1:
            report.append(f"### Files modified only in {impl1}")
            for file in only_impl1:
                report.append(f"- {file}")
            report.append("")
        
        if only_impl2:
            report.append(f"### Files modified only in {impl2}")
            for file in only_impl2:
                report.append(f"- {file}")
            report.append("")
        
        if common_files:
            report.append("### Files modified in both implementations")
            for file in common_files:
                report.append(f"- {file}")
            report.append("")
        
        # Show details for files only in one implementation
        if only_impl1:
            report.append(f"## Files Only in {impl1}")
            for file in only_impl1:
                report.append(f"### {file}")
                impl_file = impl1_dir / file
                original_file = self.dirs['original'] / file
                
                if not original_file.exists():
                    report.append("*New file in this implementation*")
                    try:
                        with open(impl_file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            if len(content) > 1000:
                                content = content[:1000] + "\n... (truncated)"
                            report.append("```")
                            report.append(content)
                            report.append("```")
                    except Exception as e:
                        report.append(f"*Error reading file: {str(e)}*")
                else:
                    report.append("*Modified file*")
                
                report.append("")
        
        if only_impl2:
            report.append(f"## Files Only in {impl2}")
            for file in only_impl2:
                report.append(f"### {file}")
                impl_file = impl2_dir / file
                original_file = self.dirs['original'] / file
                
                if not original_file.exists():
                    report.append("*New file in this implementation*")
                    try:
                        with open(impl_file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            if len(content) > 1000:
                                content = content[:1000] + "\n... (truncated)"
                            report.append("```")
                            report.append(content)
                            report.append("```")
                    except Exception as e:
                        report.append(f"*Error reading file: {str(e)}*")
                else:
                    report.append("*Modified file*")
                
                report.append("")
        
        # Compare common files
        if common_files:
            report.append("## Detailed Comparison of Common Files")
            
            for file in common_files:
                report.append(f"### {file}")
                
                original_file = self.dirs['original'] / file
                impl1_file = impl1_dir / file
                impl2_file = impl2_dir / file
                
                try:
                    # Generate diffs against original for both implementations
                    result1 = subprocess.run(
                        ['git', 'diff', '--no-index', str(original_file), str(impl1_file)],
                        capture_output=True, text=True
                    )
                    diff1 = result1.stdout if result1.returncode == 1 else ""
                    
                    result2 = subprocess.run(
                        ['git', 'diff', '--no-index', str(original_file), str(impl2_file)],
                        capture_output=True, text=True
                    )
                    diff2 = result2.stdout if result2.returncode == 1 else ""
                    
                    if diff1 == diff2:
                        report.append("*Identical changes in both implementations*")
                    else:
                        report.append("**Different implementation approaches:**")
                        
                        # Show side-by-side diff view
                        report.append(f"**{impl1} changes:**")
                        report.append("```diff")
                        report.append(diff1)
                        report.append("```")
                        
                        report.append(f"**{impl2} changes:**")
                        report.append("```diff")
                        report.append(diff2)
                        report.append("```")
                    
                except Exception as e:
                    report.append(f"*Error comparing files: {str(e)}*")
                
                report.append("")
        
        # Save or print report
        report_text = "\n".join(report)
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_text)
            print(f"✅ Comparison report saved to {output_file}")
        else:
            print(report_text)
    
    def analyze_implementation_metrics(self, impl_name: str) -> Dict:
        """Calculate code metrics for an implementation.
        
        Args:
            impl_name: Name of the implementation
            
        Returns:
            Dictionary of metrics
        """
        impl_dir = self.dirs['implementations'] / impl_name
        if not impl_dir.exists():
            print(f"❌ Error: Implementation directory {impl_name} not found")
            return {}
        
        modified_files = self.get_modified_files(impl_dir)
        
        metrics = {
            'files_modified': len(modified_files),
            'lines_added': 0,
            'lines_removed': 0,
            'complexity_indicators': 0,
            'file_types': defaultdict(int),
            'new_files': 0,
            'modified_files': 0
        }
        
        # Analyze each modified file
        for file in modified_files:
            original_file = self.dirs['original'] / file
            impl_file = impl_dir / file

            # Count file types
            file_ext = os.path.splitext(file)[1].lower()
            metrics['file_types'][file_ext] += 1
            
            # If file is new, count all lines as added
            if not original_file.exists():
                metrics['new_files'] += 1
                try:
                    with open(impl_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        metrics['lines_added'] += content.count('\n') + 1
                except Exception:
                    pass
                continue
            
            metrics['modified_files'] += 1
            
            # Get diff to count added/removed lines
            try:
                result = subprocess.run(
                    ['git', 'diff', '--no-index', str(original_file), str(impl_file)],
                    capture_output=True, text=True
                )
                diff_output = result.stdout if result.returncode == 1 else ""
                
                # Count added/removed lines
                for line in diff_output.split('\n'):
                    if line.startswith('+') and not line.startswith('+++'):
                        metrics['lines_added'] += 1
                    elif line.startswith('-') and not line.startswith('---'):
                        metrics['lines_removed'] += 1
                
                # Simple complexity indicators (very basic)
                if file_ext in ['.py', '.js', '.java', '.cpp', '.c', '.rb', '.php']:
                    try:
                        with open(impl_file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            # Count conditional statements and loops as complexity
                            patterns = [
                                r'\bif\s*\(', r'\belse\s*\{', r'\bfor\s*\(', 
                                r'\bwhile\s*\(', r'\bswitch\s*\(', r'\bcase\s*:'
                            ]
                            for pattern in patterns:
                                metrics['complexity_indicators'] += len(re.findall(pattern, content))
                    except Exception:
                        pass
            except Exception:
                pass
        
        return metrics
    
    def generate_comparison_matrix(self, output_file: Optional[Path] = None) -> None:
        """Generate a comparison matrix of all implementations.
        
        Args:
            output_file: Path to save the matrix report
        """
        implementations = self.list_implementations()
        if not implementations:
            print("❌ No implementations found to compare")
            return
        
        # Collect metrics for each implementation
        impl_metrics = {}
        for impl in implementations:
            print(f"📊 Analyzing metrics for {impl}...")
            impl_metrics[impl] = self.analyze_implementation_metrics(impl)
        
        # Generate markdown table
        report = ["# Implementation Comparison Matrix", ""]
        
        # Basic metrics table
        report.append("## Basic Metrics")
        report.append("| Implementation | Files Modified | New Files | Modified Files | Lines Added | Lines Removed | Complexity |")
        report.append("|---------------|---------------|-----------|----------------|-------------|--------------|-----------|")
        
        for impl in implementations:
            metrics = impl_metrics[impl]
            report.append(f"| {impl} | {metrics['files_modified']} | {metrics['new_files']} | {metrics['modified_files']} | {metrics['lines_added']} | {metrics['lines_removed']} | {metrics['complexity_indicators']} |")
        
        report.append("")
        
        # File types table
        all_file_types = set()
        for metrics in impl_metrics.values():
            all_file_types.update(metrics['file_types'].keys())
        
        if all_file_types:
            report.append("## File Types Modified")
            header = "| Implementation |"
            separator = "|---------------|"
            
            for file_type in sorted(all_file_types):
                type_name = file_type if file_type else "(no extension)"
                header += f" {type_name} |"
                separator += "---|"
            
            report.append(header)
            report.append(separator)
            
            for impl in implementations:
                row = f"| {impl} |"
                for file_type in sorted(all_file_types):
                    row += f" {impl_metrics[impl]['file_types'].get(file_type, 0)} |"
                report.append(row)
            
            report.append("")
        
        # Evaluation matrix template
        report.append("## Evaluation Criteria")
        report.append("*Fill in your evaluation scores for each implementation (1-5 scale, 5 being best)*")
        report.append("")
        report.append("| Criteria | " + " | ".join(implementations) + " |")
        report.append("|" + "---|" * (len(implementations) + 1))
        
        criteria = [
            "Code Quality (clarity, simplicity)",
            "Documentation",
            "Architecture Design",
            "Error Handling",
            "Maintainability",
            "Performance Efficiency", 
            "Test Coverage",
            "Overall Score"
        ]
        
        for criterion in criteria:
            report.append(f"| {criterion} | " + " | ".join(["" for _ in implementations]) + " |")
        
        report.append("")
        report.append("## Notes and Observations")
        report.append("*Add your notes about each implementation here*")
        report.append("")
        
        for impl in implementations:
            report.append(f"### {impl}")
            report.append("- ")
            report.append("")
        
        # Save or print report
        report_text = "\n".join(report)
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_text)
            print(f"✅ Comparison matrix saved to {output_file}")
        else:
            print(report_text)


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Implementation Comparison Tool")
    parser.add_argument("--dir", default="code-evaluation", 
                      help="Base directory for analysis")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List available implementations")
    
    # Report command
    report_parser = subparsers.add_parser("report", help="Generate implementation report")
    report_parser.add_argument("implementation", help="Implementation to analyze")
    report_parser.add_argument("--output", help="Output file for report")
    
    # Compare command
    compare_parser = subparsers.add_parser("compare", help="Compare two implementations")
    compare_parser.add_argument("impl1", help="First implementation")
    compare_parser.add_argument("impl2", help="Second implementation")
    compare_parser.add_argument("--output", help="Output file for comparison")
    
    # Matrix command
    matrix_parser = subparsers.add_parser("matrix", help="Generate comparison matrix")
    matrix_parser.add_argument("--output", help="Output file for matrix")
    
    args = parser.parse_args()
    
    tool = ImplementationComparison(args.dir)
    
    if args.command == "list":
        implementations = tool.list_implementations()
        if implementations:
            print("Available implementations:")
            for impl in implementations:
                print(f"- {impl}")
        else:
            print("No implementations found.")
    
    elif args.command == "report":
        output_file = Path(args.output) if args.output else None
        tool.generate_implementation_report(args.implementation, output_file)
    
    elif args.command == "compare":
        output_file = Path(args.output) if args.output else None
        tool.compare_implementations(args.impl1, args.impl2, output_file)
    
    elif args.command == "matrix":
        output_file = Path(args.output) if args.output else None
        tool.generate_comparison_matrix(output_file)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()