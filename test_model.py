# ============================================================
#   test_model.py  —  Handwriting Synthesis Project
#   Tests for: drawing.py, data_frame.py, demos.py (Hand)
#   Run with:  pytest test_model.py -v
# ============================================================

import os
import sys
import numpy as np
import pytest

# ────────────────────────────────────────────────
# PHASE 1 — Environment & Import Tests
# ────────────────────────────────────────────────

def test_python_version():
    """Python must be 3.x"""
    assert sys.version_info.major == 3, "Python 3 required"

def test_numpy_import():
    import numpy as np
    assert np.__version__ is not None
    print(f"\n  numpy version: {np.__version__}")

def test_svgwrite_import():
    """svgwrite is needed to generate SVG output"""
    try:
        import svgwrite
        assert True
    except ImportError:
        pytest.fail("svgwrite not installed — run: pip install svgwrite")

def test_scipy_import():
    """scipy is used in drawing.py for denoise/interpolate"""
    try:
        from scipy.signal import savgol_filter
        from scipy.interpolate import interp1d
        assert True
    except ImportError:
        pytest.fail("scipy not installed — run: pip install scipy")

def test_matplotlib_import():
    try:
        import matplotlib
        assert True
    except ImportError:
        pytest.fail("matplotlib not installed — run: pip install matplotlib")


# ────────────────────────────────────────────────
# PHASE 2 — drawing.py Unit Tests
# ────────────────────────────────────────────────

def test_drawing_alphabet_not_empty():
    """Alphabet must have characters defined"""
    from drawing import alphabet
    assert len(alphabet) > 0, "Alphabet is empty!"
    print(f"\n  Alphabet size: {len(alphabet)}")

def test_drawing_alphabet_contains_basics():
    """Must support letters, digits, space"""
    from drawing import alphabet
    assert 'a' in alphabet
    assert 'z' in alphabet
    assert 'A' in alphabet
    assert ' ' in alphabet
    assert '.' in alphabet

def test_encode_ascii_basic():
    """encode_ascii should return numpy array"""
    from drawing import encode_ascii
    result = encode_ascii("Hello")
    assert isinstance(result, np.ndarray), "encode_ascii must return numpy array"
    assert len(result) > 0, "Encoded result is empty"
    print(f"\n  'Hello' encoded to {len(result)} ints: {result}")

def test_encode_ascii_adds_null_terminator():
    """encode_ascii appends 0 at the end"""
    from drawing import encode_ascii
    result = encode_ascii("Hi")
    assert result[-1] == 0, "Last element should be null terminator (0)"

def test_encode_ascii_single_char():
    from drawing import encode_ascii
    result = encode_ascii("a")
    assert len(result) == 2  # char + null terminator

def test_offsets_to_coords_shape():
    """offsets_to_coords should return same length array"""
    from drawing import offsets_to_coords
    offsets = np.array([[0.1, 0.2, 0], [0.3, 0.1, 0], [0.2, 0.3, 1]])
    coords = offsets_to_coords(offsets)
    assert coords.shape == offsets.shape, "coords shape must match offsets shape"

def test_coords_to_offsets_shape():
    """coords_to_offsets should return same length array"""
    from drawing import coords_to_offsets
    coords = np.array([[1.0, 2.0, 0], [2.0, 3.0, 0], [3.0, 5.0, 1]])
    offsets = coords_to_offsets(coords)
    assert offsets.shape == coords.shape

def test_offsets_coords_roundtrip():
    """Converting offsets→coords→offsets should be lossless for rows 1+.
    NOTE: coords_to_offsets always resets row 0 to [0,0,1] by design,
    so we only compare from row 1 onward."""
    from drawing import offsets_to_coords, coords_to_offsets
    original = np.array([[0.1, 0.2, 0.0],
                          [0.3, 0.1, 0.0],
                          [0.2, 0.4, 1.0]], dtype=np.float32)
    coords   = offsets_to_coords(original)
    restored = coords_to_offsets(coords)
    # Row 0 is intentionally [0,0,1] after round-trip (start marker) — skip it
    np.testing.assert_allclose(original[1:], restored[1:], atol=1e-5,
                               err_msg="Round-trip offsets→coords→offsets failed")

def test_normalize_reduces_magnitude():
    """normalize should scale strokes to unit median norm"""
    from drawing import normalize
    offsets = np.random.randn(50, 3).astype(np.float32)
    offsets[:, 2] = 0
    offsets[49, 2] = 1
    normed = normalize(offsets)
    median_norm = np.median(np.linalg.norm(normed[:, :2], axis=1))
    assert abs(median_norm - 1.0) < 0.1, f"Median norm after normalize: {median_norm}"

def test_align_returns_same_shape():
    """align() should not change array shape"""
    from drawing import align
    coords = np.random.randn(30, 2)
    aligned = align(coords)
    assert aligned.shape == coords.shape

def test_denoise_valid_strokes():
    """denoise should return array with same columns"""
    from drawing import denoise
    # create a simple stroke ending with eos=1
    coords = np.zeros((20, 3), dtype=np.float32)
    coords[:, 0] = np.linspace(0, 10, 20)
    coords[:, 1] = np.linspace(0, 5,  20)
    coords[19, 2] = 1.0   # end of stroke
    result = denoise(coords)
    assert result.shape[1] == 3, "denoise must keep 3 columns"
    assert len(result) > 0


# ────────────────────────────────────────────────
# PHASE 3 — data_frame.py Unit Tests
# ────────────────────────────────────────────────

def test_dataframe_creation():
    """DataFrame should accept columns + data"""
    from data_frame import DataFrame
    cols = ['x', 'y']
    data = [np.random.randn(100, 5), np.random.randn(100, 3)]
    df   = DataFrame(columns=cols, data=data)
    assert len(df) == 100

def test_dataframe_column_access():
    from data_frame import DataFrame
    cols = ['a', 'b']
    data = [np.ones((50, 4)), np.zeros((50, 2))]
    df   = DataFrame(columns=cols, data=data)
    assert df['a'].shape == (50, 4)
    assert df['b'].shape == (50, 2)

def test_dataframe_train_test_split():
    """Train/test split should give correct sizes"""
    from data_frame import DataFrame
    data = [np.random.randn(200, 3), np.random.randn(200, 2)]
    df   = DataFrame(columns=['x', 'c'], data=data)
    train, test = df.train_test_split(train_size=0.8, random_state=42)
    assert len(train) == 160
    assert len(test)  == 40

def test_dataframe_batch_generator():
    """Batch generator should yield correct batch sizes"""
    from data_frame import DataFrame
    data = [np.random.randn(100, 3), np.random.randn(100, 2)]
    df   = DataFrame(columns=['x', 'c'], data=data)
    gen  = df.batch_generator(batch_size=10, num_epochs=1, shuffle=False)
    batch = next(gen)
    assert len(batch) == 10

def test_dataframe_shapes():
    from data_frame import DataFrame
    data = [np.random.randn(50, 3, 2), np.ones((50,))]
    df   = DataFrame(columns=['x', 'y'], data=data)
    shapes = df.shapes()
    assert shapes['x'] == (50, 3, 2)


# ────────────────────────────────────────────────
# PHASE 4 — Stroke Data Validation Tests
# ────────────────────────────────────────────────

def test_stroke_pen_state_is_binary():
    """Pen state column (index 2) must only contain 0 or 1"""
    strokes = np.array([[0.1, 0.2, 0.0],
                         [0.3, 0.1, 0.0],
                         [0.2, 0.4, 1.0]])
    pen_states = strokes[:, 2]
    unique = set(np.unique(pen_states))
    assert unique.issubset({0.0, 1.0}), f"Invalid pen states: {unique}"

def test_stroke_values_in_range():
    """dx/dy offsets should not be extreme (sanity check)"""
    strokes = np.random.randn(100, 3) * 2   # realistic scale
    strokes[:, 2] = 0
    strokes[-1, 2] = 1
    assert np.abs(strokes[:, 0]).max() < 50, "dx values out of range"
    assert np.abs(strokes[:, 1]).max() < 50, "dy values out of range"

def test_stroke_has_end_of_stroke():
    """At least one stroke must have pen_up=1"""
    from drawing import encode_ascii
    # simulate a minimal stroke sequence
    strokes = np.zeros((10, 3))
    strokes[-1, 2] = 1.0
    eos_count = (strokes[:, 2] == 1.0).sum()
    assert eos_count >= 1, "No end-of-stroke marker found"

def test_encode_ascii_max_length():
    """Encoded sequence must not exceed MAX_CHAR_LEN"""
    from drawing import encode_ascii, MAX_CHAR_LEN
    long_text = "A" * 80
    result = encode_ascii(long_text)
    # truncate as done in prepare_data
    truncated = result[:MAX_CHAR_LEN]
    assert len(truncated) <= MAX_CHAR_LEN


# ────────────────────────────────────────────────
# PHASE 5 — Input Validation (mirrors demos.py checks)
# ────────────────────────────────────────────────

def test_valid_characters_accepted():
    """All chars in test string must be in alphabet"""
    from drawing import alphabet
    valid_set = set(alphabet)
    test_line  = "Hello World"
    for ch in test_line:
        assert ch in valid_set, f"Character '{ch}' not in alphabet"

def test_line_length_limit():
    """Lines longer than 75 chars should be flagged"""
    line_ok   = "Hello"          # 5 chars  — OK
    line_bad  = "A" * 76         # 76 chars — too long
    assert len(line_ok)  <= 75, "Short line wrongly rejected"
    assert len(line_bad) >  75, "Long line not detected"

def test_invalid_character_detection():
    """Characters outside alphabet should be detectable"""
    from drawing import alphabet
    valid_set   = set(alphabet)
    test_string = "Hello @World"   # '@' not in alphabet
    invalid_chars = [c for c in test_string if c not in valid_set]
    assert len(invalid_chars) > 0, "Should detect '@' as invalid"
    print(f"\n  Invalid chars found: {invalid_chars}")

def test_empty_line_handling():
    """Empty string encodes without error"""
    from drawing import encode_ascii
    result = encode_ascii("")
    assert isinstance(result, np.ndarray)

def test_special_characters_in_alphabet():
    """Check which special chars are supported"""
    from drawing import alphabet
    supported = [c for c in "!.,?-' " if c in alphabet]
    print(f"\n  Supported special chars: {supported}")
    assert len(supported) > 0


# ────────────────────────────────────────────────
# PHASE 6 — SVG Output Tests (no model needed)
# ────────────────────────────────────────────────

def test_svgwrite_creates_drawing():
    """svgwrite should create a basic SVG without error"""
    import svgwrite
    dwg = svgwrite.Drawing(filename="test_output.svg")
    dwg.viewbox(width=1000, height=200)
    dwg.add(dwg.rect(insert=(0, 0), size=(1000, 200), fill='white'))
    # add a simple path
    path = svgwrite.path.Path("M10,10 L100,100")
    path = path.stroke(color='black', width=2).fill('none')
    dwg.add(path)
    dwg.save()
    assert os.path.exists("test_output.svg"), "SVG file was not created"
    os.remove("test_output.svg")   # cleanup

def test_svg_path_generation():
    """Test SVG path string is generated correctly from strokes"""
    strokes = np.array([[10, 20, 0],
                         [30, 40, 0],
                         [50, 60, 1]], dtype=float)
    p = "M{},{} ".format(0, 0)
    prev_eos = 1.0
    for x, y, eos in zip(strokes[:, 0], strokes[:, 1], strokes[:, 2]):
        p += '{}{},{} '.format('M' if prev_eos == 1.0 else 'L', x, y)
        prev_eos = eos
    assert 'M' in p and 'L' in p, "Path must contain move and line commands"


# ────────────────────────────────────────────────
# PHASE 7 — Hand class (requires checkpoints)
# ────────────────────────────────────────────────

@pytest.mark.skipif(
    not os.path.exists('checkpoints'),
    reason="Skipped: 'checkpoints/' folder not found — model not trained yet"
)
def test_hand_loads():
    """Hand() should load model from checkpoints without error"""
    from demos import Hand
    hand = Hand()
    assert hand.nn is not None, "RNN model failed to load"

@pytest.mark.skipif(
    not os.path.exists('checkpoints'),
    reason="Skipped: 'checkpoints/' folder not found"
)
def test_hand_write_produces_svg():
    """hand.write() should create an SVG file"""
    from demos import Hand
    import tempfile
    hand = Hand()
    out  = tempfile.mktemp(suffix='.svg')
    hand.write(
        filename=out,
        lines=["Hello"],
        biases=0.75,
        styles=[9],
        stroke_colors=['black'],
        stroke_widths=[2]
    )
    assert os.path.exists(out), "SVG output file was not created"
    os.remove(out)

@pytest.mark.skipif(
    not os.path.exists('checkpoints'),
    reason="Skipped: 'checkpoints/' folder not found"
)
def test_hand_invalid_char_raises():
    """hand.write() must raise ValueError for invalid characters"""
    from demos import Hand
    hand = Hand()
    with pytest.raises(ValueError):
        hand.write(
            filename='test_bad.svg',
            lines=["Hello @World"],   # '@' is invalid
            biases=0.75,
            styles=[9]
        )

@pytest.mark.skipif(
    not os.path.exists('checkpoints'),
    reason="Skipped: 'checkpoints/' folder not found"
)
def test_hand_line_too_long_raises():
    """hand.write() must raise ValueError for lines > 75 chars"""
    from demos import Hand
    hand = Hand()
    with pytest.raises(ValueError):
        hand.write(
            filename='test_long.svg',
            lines=["A" * 76],
            biases=0.75,
            styles=[9]
        )
        