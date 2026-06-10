"""Code analyzer module for analyzing and processing code files."""

# pylama:ignore=E501,E251
import os
import re
from dataclasses import dataclass
from typing import List


@dataclass
class CodeIssue:
    """Class to represent a code issue found during analysis."""

    file: str
    line: int
    issue_type: str
    message: str
    suggestion: str = None


class CodeAnalyzer:
    """Analyzes code files for potential improvements."""

    def __init__(self):
        self.max_line_length = 100
        self.max_function_length = 50
        self.max_params = 5

    def analyze_directory(self,
                          directory: str,
                          file_pattern: str = None) -> List[CodeIssue]:
        """Analyze all code files in a directory."""
        issues = []

        for root, _, files in os.walk(directory):
            for file in files:
                if file_pattern and not re.match(file_pattern, file):
                    continue

                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, directory)

                # Skip non-code files
                if not self._is_code_file(file):
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Analyze based on file type
                    if file.endswith(".py"):
                        issues.extend(
                            self._analyze_python_file(relative_path, content))
                    elif file.endswith(".js"):
                        issues.extend(
                            self._analyze_javascript_file(
                                relative_path, content))
                    else:
                        issues.extend(
                            self._analyze_generic_file(relative_path, content))
                except Exception as e:
                    print(f"Error analyzing {file_path}: {str(e)}")

        return issues

    def _is_code_file(self, filename: str) -> bool:
        """Check if a file is a code file based on extension."""
        code_extensions = {
            ".py",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".java",
            ".cpp",
            ".c",
            ".h",
            ".cs",
            ".php",
            ".rb",
            ".go",
        }
        return any(filename.endswith(ext) for ext in code_extensions)

    def _analyze_python_file(self, file_path: str,
                             content: str) -> List[CodeIssue]:
        """Analyze a Python file for potential issues."""
        issues = []
        lines = content.splitlines()

        in_function = False
        function_lines = 0

        for i, line in enumerate(lines, 1):
            # Check line length
            if len(line.strip()) > self.max_line_length:
                issues.append(
                    CodeIssue(
                        file=file_path,
                        line=i,
                        issue_type="style",
                        message=
                        f"Line exceeds {self.max_line_length} characters",
                        suggestion=
                        "Consider breaking this line into multiple lines",
                    ))

            # Check for function definitions
            if re.match(r"^\s*def\s+\w+\s*\(", line):
                in_function = True
                function_lines = 0

                # Check number of parameters
                params = re.search(r"\((.*?)\)", line)
                if params:
                    param_count = len(
                        [p for p in params.group(1).split(",") if p.strip()])
                    if param_count > self.max_params:
                        issues.append(
                            CodeIssue(
                                file=file_path,
                                line=i,
                                issue_type="complexity",
                                message=
                                f"Function has {param_count} parameters (max {self.max_params})",
                                suggestion=
                                "Consider grouping parameters into a class or using keyword arguments",
                            ))

            # Count function lines
            if in_function:
                function_lines += 1
                if function_lines > self.max_function_length:
                    issues.append(
                        CodeIssue(
                            file=file_path,
                            line=i,
                            issue_type="complexity",
                            message=
                            f"Function is {function_lines} lines long (max {self.max_function_length})",
                            suggestion=
                            "Consider breaking this function into smaller functions",
                        ))
                    in_function = False  # Only report once per function

            # Check for debugging statements
            if re.search(r"print\s*\(|pdb\.set_trace\(\)", line):
                issues.append(
                    CodeIssue(
                        file=file_path,
                        line=i,
                        issue_type="debugging",
                        message="Found debugging statement",
                        suggestion=
                        "Remove debugging statements before committing",
                    ))

        return issues

    def _analyze_javascript_file(self, file_path: str,
                                 content: str) -> List[CodeIssue]:
        """Analyze a JavaScript file for potential issues."""
        issues = []
        lines = content.splitlines()

        in_function = False
        function_lines = 0

        for i, line in enumerate(lines, 1):
            # Check line length
            if len(line.strip()) > self.max_line_length:
                issues.append(
                    CodeIssue(
                        file=file_path,
                        line=i,
                        issue_type="style",
                        message=
                        f"Line exceeds {self.max_line_length} characters",
                        suggestion=
                        "Consider breaking this line into multiple lines",
                    ))

            # Check for function definitions
            if re.search(r"(function\s+\w+\s*\(|=>|\w+\s*=\s*function\s*\()",
                         line):
                in_function = True
                function_lines = 0

                # Check number of parameters
                params = re.search(r"\((.*?)\)", line)
                if params:
                    param_count = len(
                        [p for p in params.group(1).split(",") if p.strip()])
                    if param_count > self.max_params:
                        issues.append(
                            CodeIssue(
                                file=file_path,
                                line=i,
                                issue_type="complexity",
                                message=
                                f"Function has {param_count} parameters (max {self.max_params})",
                                suggestion=
                                "Consider grouping parameters into an object or using destructuring",
                            ))

            # Count function lines
            if in_function:
                function_lines += 1
                if function_lines > self.max_function_length:
                    issues.append(
                        CodeIssue(
                            file=file_path,
                            line=i,
                            issue_type="complexity",
                            message=
                            f"Function is {function_lines} lines long (max {self.max_function_length})",
                            suggestion=
                            "Consider breaking this function into smaller functions",
                        ))
                    in_function = False  # Only report once per function

            # Check for debugging statements
            if re.search(r"console\.(log|debug|info|warn|error)\s*\(", line):
                issues.append(
                    CodeIssue(
                        file=file_path,
                        line=i,
                        issue_type="debugging",
                        message="Found console statement",
                        suggestion=
                        "Remove console statements before committing",
                    ))

        return issues

    def _analyze_generic_file(self, file_path: str,
                              content: str) -> List[CodeIssue]:
        """Analyze any code file for generic issues."""
        issues = []
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            # Check line length
            if len(line.strip()) > self.max_line_length:
                issues.append(
                    CodeIssue(
                        file=file_path,
                        line=i,
                        issue_type="style",
                        message=
                        f"Line exceeds {self.max_line_length} characters",
                        suggestion=
                        "Consider breaking this line into multiple lines",
                    ))

            # Check for TODO comments
            if re.search(r"TODO|FIXME|XXX", line, re.IGNORECASE):
                issues.append(
                    CodeIssue(
                        file=file_path,
                        line=i,
                        issue_type="documentation",
                        message="Found TODO comment",
                        suggestion="Consider addressing this TODO item",
                    ))

            # Check for hardcoded values
            if re.search(r'[\'"]\d+[\'"]|\b\d{4,}\b', line):
                issues.append(
                    CodeIssue(
                        file=file_path,
                        line=i,
                        issue_type="maintainability",
                        message="Found hardcoded value",
                        suggestion=
                        "Consider using a named constant or configuration value",
                    ))

        return issues
