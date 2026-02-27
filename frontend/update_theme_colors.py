
import os

replacements = {
    'bg-[#2B3139]/20': 'bg-gray-200 dark:bg-[#2B3139]/20',
    'bg-[#2B3139]/50': 'bg-gray-300 dark:bg-[#2B3139]/50',
    'border-[#2B3139]/50': 'border-gray-300 dark:border-[#2B3139]/50',
    'text-[#F6465D]': 'text-red-600 dark:text-[#F6465D]',
    'text-[#0ECB81]': 'text-green-600 dark:text-[#0ECB81]',
    'bg-[#F6465D]/10': 'bg-red-50 dark:bg-[#F6465D]/10',
    'bg-[#0ECB81]/10': 'bg-green-50 dark:bg-[#0ECB81]/10',
    'bg-[#F0B90B]/10': 'bg-yellow-50 dark:bg-[#F0B90B]/10',
    'bg-[#F6465D]/20': 'bg-red-100 dark:bg-[#F6465D]/20',
    'bg-[#0ECB81]/20': 'bg-green-100 dark:bg-[#0ECB81]/20',
    'hover:border-[#F0B90B]/50': 'hover:border-yellow-500/50 dark:hover:border-[#F0B90B]/50',
    'hover:text-[#F0B90B]': 'hover:text-yellow-600 dark:hover:text-[#F0B90B]', # Just in case missed by previous logic
    'accent-[#F0B90B]': 'accent-yellow-600 dark:accent-[#F0B90B]',
}

file_path = 'app/page.tsx'

with open(file_path, 'r') as f:
    content = f.read()

for old, new in replacements.items():
    content = content.replace(old, new)

with open(file_path, 'w') as f:
    f.write(content)

print(f"Updated colors in {file_path}")
