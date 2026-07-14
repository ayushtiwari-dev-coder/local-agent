# tools/skeleton_parser.py

MAX_SKELETON_LINES = 100


def _downsample_indices(indices: list[int], max_lines: int) -> tuple[list[int], bool]:
    """Uniformly downsamples a list of indices to fit within max_lines."""
    if len(indices) <= max_lines:
        return indices, False
    step = len(indices) / max_lines
    return [indices[int(i * step)] for i in range(max_lines)], True


def _get_spatial_indices(lines: list[str], exclude_indices: set[int]) -> set[int]:
    """Generates evenly spaced line indices for content previews."""
    spatial_indices = set()
    total_lines = len(lines)
    if total_lines > 40:
        step = max(1, total_lines // 40)
        for i in range(step, total_lines - 1, step):
            idx = i
            # Find nearest non-empty line
            while idx < total_lines and not lines[idx].strip():
                idx += 1
            if idx < total_lines and idx not in exclude_indices:
                spatial_indices.add(idx)
    return spatial_indices


def _build_code_skeleton(lines: list[str], ext: str) -> str:
    """CASE 1: Code files. Only extracts semantic structure (functions/classes)."""
    semantic_indices = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        if ext in ["py", "pyw"]:
            if (
                stripped.startswith("def ")
                or stripped.startswith("class ")
                or stripped.startswith("async def ")
            ):
                semantic_indices.add(i)
        elif ext in ["js", "ts", "jsx", "tsx"]:
            if (
                stripped.startswith("function ")
                or stripped.startswith("class ")
                or "=>" in stripped
                or (
                    stripped.startswith("const ")
                    and ("= function" in stripped or "= async" in stripped)
                )
            ):
                if len(stripped) < 100:
                    semantic_indices.add(i)

    if not semantic_indices:
        return "No structural data could be extracted from this code file."

    indices, is_downsampled = _downsample_indices(
        sorted(list(semantic_indices)), MAX_SKELETON_LINES
    )

    skeleton = []
    for i in indices:
        line_content = lines[i].strip()
        preview = line_content[:150] + ("..." if len(line_content) > 150 else "")
        skeleton.append(f"Line {i + 1}: {preview}")

    res = "\n".join(skeleton)
    if is_downsampled:
        res += (
            f"\n... (Skeleton downsampled to {MAX_SKELETON_LINES} items to fit context)"
        )
    return res


def _build_hybrid_skeleton(lines: list[str], semantic_indices: set[int]) -> str:
    """CASE 2: Markdown/Data files WITH headers. Merges headers and spatial previews."""
    spatial_indices = _get_spatial_indices(lines, semantic_indices)
    all_indices = sorted(list(semantic_indices | spatial_indices))

    indices, is_downsampled = _downsample_indices(all_indices, MAX_SKELETON_LINES)

    skeleton = []
    for i in indices:
        line_content = lines[i].strip()
        if i in semantic_indices:
            preview = line_content[:150] + ("..." if len(line_content) > 150 else "")
            skeleton.append(f"Line {i + 1}: {preview}")
        else:
            preview = line_content[:80] + ("..." if len(line_content) > 80 else "")
            skeleton.append(f"Line {i + 1}: [Content Preview] {preview}")

    res = "\n".join(skeleton)
    if is_downsampled:
        res += (
            f"\n... (Skeleton downsampled to {MAX_SKELETON_LINES} items to fit context)"
        )
    return res


def _build_spatial_skeleton(lines: list[str]) -> str:
    """CASE 3: Dead files (Logs, txt without headers). Pure spatial map."""
    spatial_indices = _get_spatial_indices(lines, set())
    if not spatial_indices:
        return "No structural or spatial data could be extracted."

    indices, is_downsampled = _downsample_indices(
        sorted(list(spatial_indices)), MAX_SKELETON_LINES
    )

    skeleton = [
        "No semantic structure (headers/functions) found. Generating spatial map:"
    ]
    for i in indices:
        line_content = lines[i].strip()
        preview = line_content[:80] + ("..." if len(line_content) > 80 else "")
        skeleton.append(f"Line {i + 1}: [Content Preview] {preview}")

    res = "\n".join(skeleton)
    if is_downsampled:
        res += (
            f"\n... (Skeleton downsampled to {MAX_SKELETON_LINES} items to fit context)"
        )
    return res


def generate_file_skeleton(content: str, filename: str) -> str:
    """
    Main orchestrator. Routes the file to the correct parser based on its type and contents.
    """
    if not filename:
        return ""

    lines = content.splitlines()
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    is_code_file = ext in [
        "py",
        "pyw",
        "js",
        "ts",
        "jsx",
        "tsx",
        "c",
        "cpp",
        "h",
        "java",
        "rs",
        "sh",
    ]

    # CASE 1: Code Files
    if is_code_file:
        return _build_code_skeleton(lines, ext)

    # Find headers for Data/Markdown files
    semantic_indices = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.lower().startswith("source:"):
            semantic_indices.add(i)

    # CASE 2: Hybrid Files (Has Headers)
    if semantic_indices:
        return _build_hybrid_skeleton(lines, semantic_indices)

    # CASE 3: Dead Files (No Headers)
    return _build_spatial_skeleton(lines)
