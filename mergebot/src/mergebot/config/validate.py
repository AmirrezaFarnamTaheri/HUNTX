from .schema import AppConfig

def validate_config(config: AppConfig):
    # Basic validation
    seen_ids = set()
    for s in config.sources:
        if s.id in seen_ids:
            raise ValueError(f"Duplicate source ID: {s.id}")
        seen_ids.add(s.id)

    for r in config.routes:
        for src_ref in r.from_sources:
            if src_ref not in seen_ids:
                raise ValueError(f"Route {r.name} references unknown source {src_ref}")
