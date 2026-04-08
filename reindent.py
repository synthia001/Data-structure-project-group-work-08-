with open('main.py', 'r') as f:
    lines = f.readlines()

new_lines = []
indent = False
for line in lines:
    stripped = line.strip()
    if stripped.startswith('@') or stripped.startswith('def ') or stripped.startswith('class '):
        indent = True
        new_lines.append(line)
    elif stripped == '' or stripped.startswith('#'):
        new_lines.append(line)
    elif indent:
        if stripped.startswith(' ') or stripped.startswith('\t'):
            new_lines.append(line)
        else:
            new_lines.append('    ' + line)
    else:
        new_lines.append(line)

with open('main.py', 'w') as f:
    f.writelines(new_lines)