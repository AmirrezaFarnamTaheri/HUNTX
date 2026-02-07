import os

def process_file(filepath):
    print(f"Processing {filepath}...")
    with open(filepath, 'r') as f:
        lines = f.readlines()

    new_lines = []
    skip_demo_source = False
    skip_destinations = False

    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())

        # 1. Handle demo_source removal
        if stripped.startswith("- id: demo_source"):
            skip_demo_source = True
            continue

        if skip_demo_source:
            # Stop skipping if we hit the next list item or a new section
            if stripped.startswith("- id:") or (stripped and not line.startswith(" ")):
                skip_demo_source = False
            else:
                continue

        # 2. Rename demo_output
        if "- name: demo_output" in stripped:
            new_lines.append(line.replace("demo_output", "all_sources"))
            continue

        # 3. Handle destinations removal
        # We assume destinations is inside the route we just renamed or processing
        # Since config structure is consistent, destinations: comes after formats:
        if stripped.startswith("destinations:"):
             # Only skip if we are cleaning up (we assume we want to remove all destinations for now as requested)
             # User said "Remove anything demo all over".
             # Since the only route was demo_output, we remove its destinations.
             skip_destinations = True
             continue

        if skip_destinations:
            # Stop skipping if indentation returns to route level (2 spaces) or top level (0 spaces)
            # destinations is usually at 4 spaces.
            if indent <= 2 and stripped:
                skip_destinations = False
            else:
                continue

        new_lines.append(line)

    with open(filepath, 'w') as f:
        f.writelines(new_lines)
    print(f"Updated {filepath}")

files = ['my_config.yaml', 'configs/config.prod.yaml']
for f in files:
    if os.path.exists(f):
        process_file(f)
    else:
        print(f"File {f} not found.")
