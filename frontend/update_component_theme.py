
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
    'text-[#F0B90B]': 'text-yellow-600 dark:text-[#F0B90B]',
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
    'scrollbar-thumb-[#363C45]': 'scrollbar-thumb-gray-300 dark:scrollbar-thumb-[#363C45]',
    'scrollbar-track-[#1E2329]': 'scrollbar-track-gray-100 dark:scrollbar-track-[#1E2329]',
    'hover:scrollbar-thumb-[#474D57]': 'hover:scrollbar-thumb-gray-400 dark:hover:scrollbar-thumb-[#474D57]',
    'accent-[#F0B90B]': 'accent-yellow-600 dark:accent-[#F0B90B]',
    'hover:text-[#F0B90B]': 'hover:text-yellow-600 dark:hover:text-[#F0B90B]',
}

target_dir = 'components'

for root, dirs, files in os.walk(target_dir):
    for file in files:
        if file.endswith('.tsx'):
            file_path = os.path.join(root, file)
            with open(file_path, 'r') as f:
                content = f.read()
            
            original_content = content
            for old, new in replacements.items():
                content = content.replace(old, new)
            
            if content != original_content:
                with open(file_path, 'w') as f:
                    f.write(content)
                print(f"Updated {file_path}")
