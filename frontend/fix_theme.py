
import os

file_path = 'app/page.tsx'

with open(file_path, 'r') as f:
    content = f.read()

# Fix broken hover states from previous script
content = content.replace('hover:text-yellow-600 dark:text-[#F0B90B]', 'hover:text-yellow-600 dark:hover:text-[#F0B90B]')

with open(file_path, 'w') as f:
    f.write(content)

print(f"Fixed {file_path}")
