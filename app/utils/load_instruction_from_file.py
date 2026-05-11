"""
Utilities for loading instruction files
"""

import os


def load_instruction_from_file(file_path: str) -> str:
    """Load instruction từ file markdown."""
    try:
        # Tìm file trong thư mục prompts
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(base_path, file_path)
        
        if os.path.exists(full_path):
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            print(f"⚠️ Warning: File {full_path} not found")
            return ""
    except Exception as e:
        print(f"Error reading instruction file: {e}")
        return ""
