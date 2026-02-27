
import os

replacements = {
    'bg-[#161A1E]': 'bg-gray-50 dark:bg-[#161A1E]',
    'bg-[#1E2329]': 'bg-white dark:bg-[#1E2329]',
    'text-[#EAECEF]': 'text-gray-900 dark:text-[#EAECEF]',
    'text-[#848E9C]': 'text-gray-500 dark:text-[#848E9C]',
    'border-[#2B3139]': 'border-gray-200 dark:border-[#2B3139]',
    'bg-[#2B3139]': 'bg-gray-100 dark:bg-[#2B3139]',
    'hover:bg-[#363C45]': 'hover:bg-gray-200 dark:hover:bg-[#363C45]',
    'border-[#474D57]': 'border-gray-300 dark:border-[#474D57]',
    'bg-[#0E1117]': 'bg-gray-50 dark:bg-[#0E1117]',
    'text-[#F0B90B]': 'text-yellow-600 dark:text-[#F0B90B]', # Adjust yellow for light mode visibility
}

file_path = 'app/page.tsx'

with open(file_path, 'r') as f:
    content = f.read()

for old, new in replacements.items():
    content = content.replace(old, new)

with open(file_path, 'w') as f:
    f.write(content)

print(f"Updated {file_path}")
