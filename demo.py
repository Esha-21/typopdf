import os
import logging

import numpy as np
import svgwrite

import drawing
import lyrics
from rnn import rnn


class Hand(object):

    def __init__(self):
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
        self.nn = rnn(
            log_dir='logs',
            checkpoint_dir='checkpoints',
            prediction_dir='predictions',
            learning_rates=[.0001, .00005, .00002],
            batch_sizes=[32, 64, 64],
            patiences=[1500, 1000, 500],
            beta1_decays=[.9, .9, .9],
            validation_batch_size=32,
            optimizer='rms',
            num_training_steps=100000,
            warm_start_init_step=17900,
            regularization_constant=0.0,
            keep_prob=1.0,
            enable_parameter_averaging=False,
            min_steps_to_checkpoint=2000,
            log_interval=20,
            logging_level=logging.CRITICAL,
            grad_clip=10,
            lstm_size=400,
            output_mixture_components=20,
            attention_mixture_components=10
        )
        self.nn.restore()

    def write(self, filename, lines, biases=None, styles=None, stroke_colors=None, stroke_widths=None):
        valid_char_set = set(drawing.alphabet)
        for line_num, line in enumerate(lines):
            if len(line) > 75:
                raise ValueError(
                    (
                        "Each line must be at most 75 characters. "
                        "Line {} contains {}"
                    ).format(line_num, len(line))
                )

            for char in line:
                if char not in valid_char_set:
                    raise ValueError(
                        (
                            "Invalid character {} detected in line {}. "
                            "Valid character set is {}"
                        ).format(char, line_num, valid_char_set)
                    )

        strokes = self._sample(lines, biases=biases, styles=styles)
        self._draw(strokes, lines, filename, stroke_colors=stroke_colors, stroke_widths=stroke_widths)

    def _sample(self, lines, biases=None, styles=None):
        num_samples = len(lines)
        max_tsteps = 40*max([len(i) for i in lines])
        biases = float(biases[0]) if isinstance(biases, (list, np.ndarray)) else float(biases if biases is not None else 0.5)

        x_prime = np.zeros([num_samples, 1200, 3])
        x_prime_len = np.zeros([num_samples])
        chars = np.zeros([num_samples, 120])
        chars_len = np.zeros([num_samples])

        if styles is not None:
            for i, (cs, style) in enumerate(zip(lines, styles)):
                x_p = np.load('styles/style-{}-strokes.npy'.format(style))
                c_p = np.load('styles/style-{}-chars.npy'.format(style)).tostring().decode('utf-8')

                c_p = str(c_p) + " " + cs
                c_p = drawing.encode_ascii(c_p)
                c_p = np.array(c_p)

                x_prime[i, :len(x_p), :] = x_p
                x_prime_len[i] = len(x_p)
                chars[i, :len(c_p)] = c_p
                chars_len[i] = len(c_p)

        else:
            for i in range(num_samples):
                encoded = drawing.encode_ascii(lines[i])
                chars[i, :len(encoded)] = encoded
                chars_len[i] = len(encoded)

        [samples] = self.nn.session.run(
            [self.nn.sampled_sequence],
            feed_dict={
                self.nn.prime: styles is not None,
                self.nn.x_prime: x_prime,
                self.nn.x_prime_len: x_prime_len,
                self.nn.num_samples: num_samples,
                self.nn.sample_tsteps: max_tsteps,
                self.nn.c: chars,
                self.nn.c_len: chars_len,
                self.nn.bias: biases
            }
        )
        samples = [sample[~np.all(sample == 0.0, axis=1)] for sample in samples]
        return samples

    def _draw(self, strokes, lines, filename, stroke_colors=None, stroke_widths=None):
        stroke_colors = stroke_colors or ['black']*len(lines)
        stroke_widths = stroke_widths or [2]*len(lines)

        line_height = 60
        view_width = 1000
        view_height = line_height*(len(strokes) + 1)

        dwg = svgwrite.Drawing(filename=filename)
        dwg.viewbox(width=view_width, height=view_height)
        dwg.add(dwg.rect(insert=(0, 0), size=(view_width, view_height), fill='white'))

        initial_coord = np.array([0, -(3*line_height / 4)])
        for offsets, line, color, width in zip(strokes, lines, stroke_colors, stroke_widths):

            if not line:
                initial_coord[1] -= line_height
                continue

            offsets[:, :2] *= 1.5
            strokes = drawing.offsets_to_coords(offsets)
            strokes = drawing.denoise(strokes)
            strokes[:, :2] = drawing.align(strokes[:, :2])

            strokes[:, 1] *= -1
            strokes[:, :2] -= strokes[:, :2].min() + initial_coord
            strokes[:, 0] += (view_width - strokes[:, 0].max()) / 2

            prev_eos = 1.0
            p = "M{},{} ".format(0, 0)
            for x, y, eos in zip(*strokes.T):
                p += '{}{},{} '.format('M' if prev_eos == 1.0 else 'L', x, y)
                prev_eos = eos
            path = svgwrite.path.Path(p)
            path = path.stroke(color=color, width=width, linecap='round').fill("none")
            dwg.add(path)

            initial_coord[1] -= line_height

        dwg.save()


# ===============================================
# GLOBAL HAND INSTANCE (Singleton Pattern)
# ===============================================
_hand_instance = None

def _get_hand_instance():
    """
    Get or create the Hand instance (singleton pattern).
    This avoids loading the model multiple times.
    """
    global _hand_instance
    if _hand_instance is None:
        print("🔄 Initializing handwriting model... (this may take a moment)")
        _hand_instance = Hand()
        print("✅ Model loaded successfully!")
    return _hand_instance


# ===============================================
# GENERATE_HANDWRITING FUNCTION (Flask Compatible)
# ===============================================
def generate_handwriting(text, output_path, style=0, bias=0.75, ink_color='#000000'):
    """
    Generate handwritten text as SVG file.
    
    Parameters:
    -----------
    text : str
        The text to convert to handwriting. Can contain multiple lines 
        separated by newline characters.
    
    output_path : str
        Full path where the SVG file will be saved.
        Example: 'output/result.svg'
    
    style : int, optional
        Handwriting style number (0-12). Default is 0.
        - 0: Clean/Exam style
        - 3: Casual
        - 5: Compact
        - 8: Decorative
        - 11: Natural
    
    bias : float, optional
        Handwriting bias/randomness (0.0-1.0). Default is 0.75.
        - Lower values (0.2-0.5): More uniform/predictable
        - Higher values (0.7-0.9): More variation/natural
    
    ink_color : str, optional
        Hex color code for the ink. Default is '#000000' (black).
        Examples: '#0000FF' (blue), '#00008B' (dark blue)
    
    Returns:
    --------
    None (saves SVG file to output_path)
    
    Example:
    --------
    >>> generate_handwriting(
    ...     text="Hello World!\\nThis is line 2",
    ...     output_path="output/hello.svg",
    ...     style=0,
    ...     bias=0.75,
    ...     ink_color='#000000'
    ... )
    """
    # Get Hand instance
    hand = _get_hand_instance()
    
    # Split text into lines (max 75 chars per line)
    lines = text.split('\n')
    
    # Split long lines into chunks of 75 characters
    processed_lines = []
    for line in lines:
        if len(line) <= 75:
            processed_lines.append(line)
        else:
            # Split long line into chunks
            words = line.split(' ')
            current_line = ""
            for word in words:
                if len(current_line) + len(word) + 1 <= 75:
                    current_line += (" " if current_line else "") + word
                else:
                    if current_line:
                        processed_lines.append(current_line)
                    current_line = word
            if current_line:
                processed_lines.append(current_line)
    
    lines = processed_lines
    
    # Prepare parameters for each line
    biases = [bias for _ in lines]
    styles = [style for _ in lines]
    stroke_colors = [ink_color for _ in lines]
    stroke_widths = [2 for _ in lines]
    
    # Generate handwriting
    hand.write(
        filename=output_path,
        lines=lines,
        biases=biases,
        styles=styles,
        stroke_colors=stroke_colors,
        stroke_widths=stroke_widths
    )
    
    print(f"✅ Handwriting saved to: {output_path}")


# ===============================================
# MAIN EXECUTION (Demo Examples)
# ===============================================
if __name__ == '__main__':
    # Create output directory if it doesn't exist
    os.makedirs('img', exist_ok=True)
    
    print("=" * 60)
    print("HANDWRITING SYNTHESIS DEMO")
    print("=" * 60)
    
    # Demo 1: Simple usage with generate_handwriting function
    print("\n[Demo 1] Simple text generation...")
    generate_handwriting(
        text="Hello, this is a test of the handwriting synthesis system!",
        output_path='img/demo1_simple.svg',
        style=0,
        bias=0.75,
        ink_color='#000000'
    )
    
    # Demo 2: Multi-line text
    print("\n[Demo 2] Multi-line text...")
    multi_line_text = """This is line one.
This is line two.
And this is line three!"""
    
    generate_handwriting(
        text=multi_line_text,
        output_path='img/demo2_multiline.svg',
        style=3,
        bias=0.6,
        ink_color='#0000FF'
    )
    
    # Demo 3: Different styles
    print("\n[Demo 3] Testing different styles...")
    for style_num in [0, 3, 5, 8, 11]:
        generate_handwriting(
            text=f"This is handwriting style {style_num}",
            output_path=f'img/demo3_style{style_num}.svg',
            style=style_num,
            bias=0.75,
            ink_color='#000000'
        )
    
    # Demo 4: Long text (auto-splits lines)
    print("\n[Demo 4] Long text with auto-split...")
    long_text = (
        "This is a very long sentence that exceeds the 75 character limit "
        "and should be automatically split into multiple lines by the "
        "generate_handwriting function to ensure proper rendering."
    )
    generate_handwriting(
        text=long_text,
        output_path='img/demo4_long.svg',
        style=0,
        bias=0.75,
        ink_color='#00008B'
    )
    
    print("\n" + "=" * 60)
    print("ALL DEMOS COMPLETED SUCCESSFULLY!")
    print("Check the 'img/' folder for generated SVG files.")
    print("=" * 60)