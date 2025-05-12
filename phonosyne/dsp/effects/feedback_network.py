"""
Phonosyne - Multi-Feedback Network (MFN) Effect

This module implements a flexible multi-feedback network effect.
It allows for constructing arbitrary graphs of interconnected nodes,
each with its own delay line, gain, and optional processing.

The core of the MFN is a block-based processing engine that can run
either with pure NumPy or be JIT-compiled with Numba for performance.
"""

import logging  # Added
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

# Core numerics and Numba availability
import numpy as np

# Setup logger for this module
logger = logging.getLogger(__name__)  # Added

try:
    import numba as nb

    NB_AVAILABLE = True
except ModuleNotFoundError:
    NB_AVAILABLE = False

NUMERIC_DTYPE = np.float32

# Dataclasses for graph definition will go here


@dataclass
class MFNNode:
    """A single node in the MFN graph."""

    id: str
    delay_samples: int = 0  # Delay in samples for this node's output before feedback
    gain: float = 1.0  # Gain applied to this node's output
    # Future: Add fields for per-node processing (e.g., filter type, params)
    # Example: filter_type: Optional[str] = None
    # Example: filter_params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.delay_samples < 0:
            raise ValueError("Node delay_samples cannot be negative.")
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Node id must be a non-empty string.")


@dataclass
class MFNConnection:
    """A connection between two nodes in the MFN graph."""

    source_id: str  # ID of the source node
    target_id: str  # ID of the target node
    gain: float = 1.0  # Gain applied to the signal along this connection
    delay_samples: int = 0  # Additional delay in samples for this specific connection

    def __post_init__(self):
        if self.delay_samples < 0:
            raise ValueError("Connection delay_samples cannot be negative.")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("Connection source_id must be a non-empty string.")
        if not isinstance(self.target_id, str) or not self.target_id.strip():
            raise ValueError("Connection target_id must be a non-empty string.")


@dataclass
class MFNGraph:
    """Represents the entire MFN graph structure."""

    nodes: List[MFNNode] = field(default_factory=list)
    connections: List[MFNConnection] = field(default_factory=list)
    input_gain: float = 1.0  # Gain applied to the external input signal
    output_gain: float = 1.0  # Gain applied to the final mixed output
    # Global parameters
    max_delay_samples: Optional[int] = (
        None  # Optional: if not provided, calculated from nodes/connections
    )
    chaos_level: float = 0.0  # 0.0 to 1.0, influences internal saturation/nonlinearity

    def __post_init__(self):
        if not (0.0 <= self.chaos_level <= 1.0):
            raise ValueError("chaos_level must be between 0.0 and 1.0.")

        node_ids = {node.id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("Duplicate node IDs found in the graph.")

        for conn in self.connections:
            if conn.source_id not in node_ids:
                raise ValueError(
                    f"Connection source_id '{conn.source_id}' not found in nodes."
                )
            if conn.target_id not in node_ids:
                raise ValueError(
                    f"Connection target_id '{conn.target_id}' not found in nodes."
                )

        if self.max_delay_samples is not None and self.max_delay_samples < 0:
            raise ValueError("max_delay_samples cannot be negative if specified.")
        elif self.max_delay_samples is None:
            # Calculate from graph if not provided
            current_max_delay = 0
            for node in self.nodes:
                current_max_delay = max(current_max_delay, node.delay_samples)
            for conn in self.connections:
                current_max_delay = max(current_max_delay, conn.delay_samples)
            # Add a small buffer for safety, e.g., block size, if relevant later
            # For now, just the max of specified delays.
            # This might need refinement based on how delays are used in processing.
            # If individual connection delays are relative to node output buffers,
            # then node.delay_samples + conn.delay_samples might be needed.
            # Assuming for now they are independent maximums that need to be accommodated.
            self.max_delay_samples = current_max_delay


# DSP kernels (_process_block_numpy, _process_block_numba) will go here


def _get_node_by_id(nodes_list: List[MFNNode], node_id: str) -> Optional[MFNNode]:
    """Helper to find a node in a list by its ID."""
    for node in nodes_list:
        if node.id == node_id:
            return node
    return None


def _ring_buffer_write(
    buffer: np.ndarray, write_pos: int, data_block: np.ndarray
) -> int:
    """
    Writes a block of data into a ring buffer.

    Args:
        buffer: The NumPy array representing the ring buffer.
        write_pos: The starting index in the buffer where the data_block should be written.
        data_block: The NumPy array of data to write.

    Returns:
        The new write position after writing the block.
    """
    block_size = len(data_block)
    buffer_len = len(buffer)

    if write_pos + block_size <= buffer_len:
        buffer[write_pos : write_pos + block_size] = data_block
    else:
        num_first_part = buffer_len - write_pos
        buffer[write_pos:] = data_block[:num_first_part]
        num_second_part = block_size - num_first_part
        buffer[:num_second_part] = data_block[num_first_part:]

    return (write_pos + block_size) % buffer_len


def _ring_buffer_read(
    buffer: np.ndarray,
    write_pos: int,  # Current position where *next* write would start
    delay_samples: int,
    block_size: int,
) -> np.ndarray:
    """
    Reads a block of data from a ring buffer with a specified delay.

    Args:
        buffer: The NumPy array representing the ring buffer.
        write_pos: The starting index in the buffer where the *current* block is notionally being/has been written.
                   The read operation looks backwards from this position.
        delay_samples: The number of samples of delay. delay_samples=0 reads the most recent data.
        block_size: The number of samples in the block to read.

    Returns:
        A NumPy array containing the read data block.
    """
    buffer_len = len(buffer)

    # Calculate the starting point for reading.
    # write_pos is where the current block starts.
    # Reading 'delay_samples' ago means starting at (write_pos - delay_samples).
    read_start_idx = (
        write_pos - delay_samples - block_size + buffer_len + buffer_len
    ) % buffer_len
    # The above was too complex. Simpler:
    # The end of the block to read is `delay_samples` "before" `write_pos`.
    # read_tap_end = (write_pos - delay_samples + buffer_len) % buffer_len
    # read_tap_start = (read_tap_end - block_size + buffer_len) % buffer_len

    # Let's use a convention where write_pos is the beginning of the *current* data being processed.
    # A delay of D means we want data that was written D samples prior to this current data.
    # So, the read head is at (write_pos - D)
    read_head_start = (write_pos - delay_samples + buffer_len) % buffer_len

    output_block = np.empty(block_size, dtype=buffer.dtype)

    if read_head_start + block_size <= buffer_len:
        output_block[:] = buffer[read_head_start : read_head_start + block_size]
    else:
        num_first_part = buffer_len - read_head_start
        output_block[:num_first_part] = buffer[read_head_start:]
        num_second_part = block_size - num_first_part
        output_block[num_first_part:] = buffer[:num_second_part]

    return output_block


def _process_block_numpy(
    current_input_block: np.ndarray,
    graph: MFNGraph,
    node_defs_map: Dict[str, MFNNode],  # Precomputed map for efficiency
    delay_lines_nodes: Dict[str, np.ndarray],
    current_write_pos_nodes: Dict[str, int],
    block_size: int,
) -> Tuple[np.ndarray, float, Dict[str, int]]:
    """
    Processes one block of audio using NumPy.
    Assumes connection.delay_samples == 0 for all connections.
    """

    # Initialize inputs for each node for the current block
    node_block_accumulators: Dict[str, np.ndarray] = {
        node_id: np.zeros(block_size, dtype=NUMERIC_DTYPE) for node_id in node_defs_map
    }

    # 1. Global Input Distribution
    scaled_global_input = current_input_block * graph.input_gain
    for node_id in node_defs_map:
        node_block_accumulators[node_id] += scaled_global_input

    # 2. Gather Feedback (from previous state of delay lines)
    for conn in graph.connections:
        if conn.delay_samples != 0:
            raise NotImplementedError(
                "Connection-specific delays (connection.delay_samples != 0) "
                "are not supported in this NumPy kernel version."
            )

        source_node_def = node_defs_map[conn.source_id]
        target_node_id = conn.target_id

        # Read from source_node's delay line at its specific delay_samples tap point
        # current_write_pos_nodes[source_node_def.id] is where the current block for this node starts
        delayed_signal_from_source_node_tap = _ring_buffer_read(
            buffer=delay_lines_nodes[source_node_def.id],
            write_pos=current_write_pos_nodes[
                source_node_def.id
            ],  # write_pos for the current block
            delay_samples=source_node_def.delay_samples,
            block_size=block_size,
        )

        # Apply source node's gain
        source_node_output_after_gain = (
            delayed_signal_from_source_node_tap * source_node_def.gain
        )

        # Apply connection's gain
        feedback_to_target = source_node_output_after_gain * conn.gain
        node_block_accumulators[target_node_id] += feedback_to_target

    # 3. Process Nodes (apply chaos, write to delay lines) & Calculate Mixed Output Contributions
    mixed_output_for_current_block = np.zeros(block_size, dtype=NUMERIC_DTYPE)
    new_write_pos_nodes = current_write_pos_nodes.copy()

    for node_id, node_def in node_defs_map.items():
        signal_to_write = node_block_accumulators[node_id]

        # Apply chaos/saturation if enabled
        if graph.chaos_level > 0:
            # Soft saturation, strength controlled by chaos_level
            # Factor from 1.0 (no chaos) to e.g. 6.0 (max chaos for stronger effect)
            saturation_factor = 1.0 + (graph.chaos_level * 5.0)

            # Apply gain before tanh, then attenuate after
            # This keeps signal levels somewhat consistent while increasing distortion
            temp_signal = signal_to_write * saturation_factor
            temp_signal = np.tanh(temp_signal)  # Output is in [-1, 1]
            signal_to_write = temp_signal / saturation_factor  # Rescale

            # Ensure clipping to prevent unexpected blow-ups if factor is small or signal large
            signal_to_write = np.clip(signal_to_write, -1.0, 1.0)

        # Write the processed sum into the node's delay line
        new_write_pos_nodes[node_id] = _ring_buffer_write(
            buffer=delay_lines_nodes[node_id],
            write_pos=current_write_pos_nodes[node_id],
            data_block=signal_to_write,
        )

        # Output contribution of this node to the final mix:
        # Read from its delay line (which now contains the signal_to_write for the current block period)
        # at its specific tap point, then apply node gain.
        current_node_tap_output = _ring_buffer_read(
            buffer=delay_lines_nodes[node_id],
            write_pos=new_write_pos_nodes[
                node_id
            ],  # Use new_write_pos as it's the reference for "after write"
            delay_samples=node_def.delay_samples,  # Node's specific delay tap
            block_size=block_size,
        )
        mixed_output_for_current_block += current_node_tap_output * node_def.gain

    # 4. Final Output Scaling
    final_block_output = mixed_output_for_current_block * graph.output_gain
    final_block_output = np.clip(
        final_block_output, -1.0, 1.0
    )  # Hard clip final output

    # 5. RMS Calculation
    rms_value = (
        np.sqrt(np.mean(np.square(final_block_output))) if block_size > 0 else 0.0
    )

    return final_block_output, float(rms_value), new_write_pos_nodes


if NB_AVAILABLE:

    @nb.jit(nopython=True)
    def _ring_buffer_write_nb(
        buffer: nb.float32[::1],  # 1D float32 array
        write_pos: nb.int_,  # Numba integer
        data_block: nb.float32[::1],  # 1D float32 array
    ) -> nb.int_:  # Return Numba integer
        block_size = len(data_block)
        buffer_len = len(buffer)

        if write_pos + block_size <= buffer_len:
            buffer[write_pos : write_pos + block_size] = data_block
        else:
            num_first_part = buffer_len - write_pos
            buffer[write_pos:] = data_block[:num_first_part]
            num_second_part = block_size - num_first_part
            buffer[:num_second_part] = data_block[num_first_part:]

        return (write_pos + block_size) % buffer_len

    @nb.jit(nopython=True)
    def _ring_buffer_read_nb(
        buffer: nb.float32[::1],  # 1D float32 array
        write_pos: nb.int_,  # Numba integer
        delay_samples: nb.int_,  # Numba integer
        block_size: nb.int_,  # Numba integer
    ) -> nb.float32[::1]:  # Return 1D float32 array
        buffer_len = len(buffer)
        read_head_start = (write_pos - delay_samples + buffer_len) % buffer_len

        output_block = np.empty(block_size, dtype=nb.float32)

        if read_head_start + block_size <= buffer_len:
            output_block[:] = buffer[read_head_start : read_head_start + block_size]
        else:
            num_first_part = buffer_len - read_head_start
            output_block[:num_first_part] = buffer[read_head_start:]
            num_second_part = block_size - num_first_part
            output_block[num_first_part:] = buffer[:num_second_part]

        return output_block

    @nb.jit(nopython=True)
    def _process_block_numba(
        current_input_block: nb.float32[::1],
        graph_input_gain: nb.float32,
        graph_output_gain: nb.float32,
        graph_chaos_level: nb.float32,
        node_ids_list: Any,  # Must be nb.typed.List(nb.types.unicode_type) from caller
        node_gains_arr: nb.float32[::1],
        node_delays_arr: nb.int_[::1],
        conn_source_indices: nb.int_[::1],
        conn_target_indices: nb.int_[::1],
        conn_gains_arr: nb.float32[::1],
        conn_delay_samples_arr: nb.int_[::1],
        delay_lines_nodes: Any,  # Must be nb.typed.Dict(nb.types.unicode_type, nb.float32[::1]) from caller
        current_write_pos_nodes: Any,  # Must be nb.typed.Dict(nb.types.unicode_type, nb.int_) from caller
        block_size: nb.int_,
    ):
        # The Numba JIT compiler will infer the types of node_ids_list,
        # delay_lines_nodes, and current_write_pos_nodes at runtime
        # when they are passed as Numba typed.List and typed.Dict instances.

        node_block_accumulators = nb.typed.Dict.empty(
            key_type=nb.types.unicode_type, value_type=nb.float32[::1]
        )
        for i in range(len(node_ids_list)):
            node_id = node_ids_list[i]
            node_block_accumulators[node_id] = np.zeros(block_size, dtype=nb.float32)

        scaled_global_input = current_input_block * graph_input_gain
        for i in range(len(node_ids_list)):
            node_id = node_ids_list[i]
            node_block_accumulators[node_id] += scaled_global_input

        for i in range(len(conn_source_indices)):
            source_node_idx = conn_source_indices[i]
            target_node_idx = conn_target_indices[i]

            source_node_id = node_ids_list[source_node_idx]
            target_node_id = node_ids_list[target_node_idx]

            conn_gain = conn_gains_arr[i]

            source_node_delay_samples = node_delays_arr[
                source_node_idx
            ]  # Corrected: source_node_idx
            source_node_gain = node_gains_arr[
                source_node_idx
            ]  # Corrected: source_node_idx

            delayed_signal_from_source_node_tap = _ring_buffer_read_nb(
                buffer=delay_lines_nodes[source_node_id],
                write_pos=current_write_pos_nodes[source_node_id],
                delay_samples=source_node_delay_samples,
                block_size=block_size,
            )

            source_node_output_after_gain = (
                delayed_signal_from_source_node_tap * source_node_gain
            )
            feedback_to_target = source_node_output_after_gain * conn_gain
            node_block_accumulators[target_node_id] += feedback_to_target

        mixed_output_for_current_block = np.zeros(block_size, dtype=nb.float32)

        for i in range(len(node_ids_list)):
            node_id = node_ids_list[i]
            node_gain = node_gains_arr[i]
            node_delay_samples = node_delays_arr[i]

            signal_to_write = node_block_accumulators[node_id]

            if graph_chaos_level > 0:
                saturation_factor = 1.0 + (graph_chaos_level * 5.0)
                temp_signal = signal_to_write * saturation_factor
                temp_signal = np.tanh(temp_signal)
                signal_to_write = temp_signal / saturation_factor
                for j in range(block_size):
                    val = signal_to_write[j]
                    if val < -1.0:
                        signal_to_write[j] = -1.0
                    elif val > 1.0:
                        signal_to_write[j] = 1.0

            new_pos = _ring_buffer_write_nb(
                buffer=delay_lines_nodes[node_id],
                write_pos=current_write_pos_nodes[node_id],
                data_block=signal_to_write,
            )
            current_write_pos_nodes[node_id] = new_pos

            current_node_tap_output = _ring_buffer_read_nb(
                buffer=delay_lines_nodes[node_id],
                write_pos=new_pos,
                delay_samples=node_delay_samples,
                block_size=block_size,
            )
            mixed_output_for_current_block += current_node_tap_output * node_gain

        final_block_output = mixed_output_for_current_block * graph_output_gain
        for j in range(block_size):
            val = final_block_output[j]
            if val < -1.0:
                final_block_output[j] = -1.0
            elif val > 1.0:
                final_block_output[j] = 1.0

        rms_val_sq_sum = nb.float32(0.0)
        if block_size > 0:
            for x_i in final_block_output:
                rms_val_sq_sum += x_i * x_i
            rms_value = np.sqrt(rms_val_sq_sum / block_size)
        else:
            rms_value = nb.float32(0.0)

        # Numba infers the return type for the tuple, including the typed dict
        return final_block_output, rms_value, current_write_pos_nodes


# RMS watchdog helper
def _rms_watchdog_update(
    current_rms: float,
    avg_rms: float,
    # threshold: float, # This was from a more complex version, simplified for now
    attack_coeff: float,
    release_coeff: float,
    limit_threshold_rms: float,
    max_reduction_db: float = -12.0,
) -> Tuple[float, float]:
    """
    Updates average RMS and calculates a gain reduction factor if RMS exceeds a limit threshold.
    Returns (new_avg_rms, gain_factor).
    Gain factor is 1.0 if no limiting is applied.
    """
    # Update average RMS (simple one-pole smoother)
    if current_rms > avg_rms:
        avg_rms = avg_rms * (1.0 - attack_coeff) + current_rms * attack_coeff
    else:
        avg_rms = avg_rms * (1.0 - release_coeff) + current_rms * release_coeff

    gain_factor = 1.0
    if avg_rms > limit_threshold_rms:
        # Simple proportional reduction for overshoot.
        # This is a very basic limiter.
        overshoot_rms = avg_rms - limit_threshold_rms

        # Determine a reduction amount. For simplicity, let's say for every 0.1 RMS over,
        # we apply some dB of reduction, up to max_reduction_db.
        # This is not standard but aims for a simple reduction.
        # A more robust limiter would use dB for thresholds and reduction.

        # Example: if limit_threshold_rms is 0.5, and avg_rms is 0.6 (overshoot 0.1)
        # we might want to reduce by a certain amount.
        # Let's try to map overshoot to a reduction factor directly.
        # If avg_rms is, say, 20% over limit_threshold_rms, maybe reduce gain by 20%?
        # reduction = overshoot_rms / (avg_rms + 1e-9) # Proportional reduction

        # Alternative: Fixed reduction when over threshold, scaled by how much over.
        # This is tricky to make 'sound good' without proper attack/release on the gain itself.

        # Let's use a simpler approach: if avg_rms > limit_threshold_rms,
        # calculate how many dB it is over (approx).
        # This is still not ideal as RMS isn't directly dB, but for a rough control:

        # If avg_rms is, for example, 0.7 and limit_threshold_rms is 0.5
        # A more direct approach for gain reduction:
        # Try to bring avg_rms back towards limit_threshold_rms
        desired_reduction_factor = limit_threshold_rms / (
            avg_rms + 1e-9
        )  # add epsilon to avoid div by zero

        max_reduction_linear = 10 ** (max_reduction_db / 20.0)  # e.g., 0.25 for -12dB

        gain_factor = min(1.0, desired_reduction_factor)
        gain_factor = max(max_reduction_linear, gain_factor)

    gain_factor = max(0.0, min(1.0, gain_factor))  # Ensure 0 <= gain_factor <= 1

    return avg_rms, gain_factor


# Public API (apply_mfn function, MFN class) will go here


def apply_feedback_network(
    audio_data: np.ndarray,
    graph: MFNGraph,
    sample_rate: int,
    block_size: int = 256,  # Default block size, can be tuned
    use_numba: bool = True,
    enable_rms_watchdog: bool = True,
    watchdog_threshold_rms: float = 0.707,  # RMS level to start watching closely (approx -3dBFS for sine)
    watchdog_limit_threshold_rms: float = 0.85,  # RMS level above which limiting starts (approx -1.4dBFS for sine)
    watchdog_attack_coeff: float = 0.05,  # Faster attack for watchdog avg RMS
    watchdog_release_coeff: float = 0.005,  # Slower release for watchdog avg RMS
    watchdog_max_reduction_db: float = -18.0,
) -> np.ndarray:
    """
    Applies the Multi-Feedback Network (MFN) effect to the input audio data.

    Args:
        audio_data: NumPy array of input audio data (mono).
        graph: MFNGraph object defining the network structure.
        sample_rate: Sample rate of the audio data.
        block_size: Processing block size in samples.
        use_numba: If True and Numba is available, use JIT-compiled kernels.
        enable_rms_watchdog: If True, enables an RMS-based limiter to prevent excessive loudness.
        watchdog_threshold_rms: (Not directly used in current simplified watchdog) RMS level for potential future use.
        watchdog_limit_threshold_rms: RMS level above which the watchdog starts reducing gain.
        watchdog_attack_coeff: Attack coefficient for the RMS averager in the watchdog.
        watchdog_release_coeff: Release coefficient for the RMS averager in the watchdog.
        watchdog_max_reduction_db: Maximum gain reduction applied by the watchdog in dB.

    Returns:
        NumPy array of processed audio data.
    """
    if not isinstance(audio_data, np.ndarray) or audio_data.ndim != 1:
        raise ValueError("audio_data must be a 1D NumPy array.")
    if not isinstance(graph, MFNGraph):
        raise ValueError("graph must be an MFNGraph instance.")
    if not graph.nodes:
        logger.warning("MFNGraph has no nodes. Returning original audio.")
        return audio_data.copy()

    num_samples = len(audio_data)
    output_audio = np.zeros_like(audio_data, dtype=NUMERIC_DTYPE)

    # Initialize delay lines and write positions for each node
    delay_lines_nodes: Dict[str, np.ndarray] = {}
    current_write_pos_nodes: Dict[str, int] = {}
    max_total_delay_samples = 0

    for node in graph.nodes:
        # Ensure max_delay_s is positive and reasonable
        max_delay_s = max(0.001, node.max_delay_s)  # Min 1ms delay buffer
        delay_line_len = int(max_delay_s * sample_rate)
        if (
            delay_line_len < block_size * 2
        ):  # Ensure buffer is at least 2 blocks, or a minimum reasonable size
            delay_line_len = max(block_size * 2, 256)
        delay_lines_nodes[node.id] = np.zeros(delay_line_len, dtype=NUMERIC_DTYPE)
        current_write_pos_nodes[node.id] = 0
        if node.delay_s * sample_rate > delay_line_len:
            logger.warning(
                f"Node {node.id} delay_s {node.delay_s}s exceeds its max_delay_s {max_delay_s}s buffer. Clamping delay."
            )
        max_total_delay_samples = max(
            max_total_delay_samples, int(node.delay_s * sample_rate)
        )

    # RMS Watchdog state
    avg_rms = 0.0
    watchdog_gain = 1.0

    # Prepare data structures for Numba if selected
    use_numba_effective = use_numba and NB_AVAILABLE

    # These will be passed to the Numba kernel
    # Convert node data to arrays for Numba
    node_ids_list_py = [node.id for node in graph.nodes]
    node_gains_arr_py = np.array(
        [node.gain for node in graph.nodes], dtype=NUMERIC_DTYPE
    )
    # Ensure node delays are in samples and non-negative
    node_delays_arr_py = np.array(
        [
            max(
                0,
                min(
                    int(node.delay_s * sample_rate), len(delay_lines_nodes[node.id]) - 1
                ),
            )
            for node in graph.nodes
        ],
        dtype=np.int_,
    )

    # Convert connection data to arrays for Numba
    # Create mapping from node_id to index for quick lookup
    node_id_to_idx = {node_id: i for i, node_id in enumerate(node_ids_list_py)}

    conn_source_indices_py = np.array(
        [node_id_to_idx[conn.source_node_id] for conn in graph.connections],
        dtype=np.int_,
    )
    conn_target_indices_py = np.array(
        [node_id_to_idx[conn.target_node_id] for conn in graph.connections],
        dtype=np.int_,
    )
    conn_gains_arr_py = np.array(
        [conn.gain for conn in graph.connections], dtype=NUMERIC_DTYPE
    )
    # Connection-specific delays (in samples, currently MFNConnection.delay_s is not used in kernel)
    # For now, these are zero, but the structure is here for future use.
    conn_delay_samples_arr_py = np.array(
        [max(0, int(conn.delay_s * sample_rate)) for conn in graph.connections],
        dtype=np.int_,
    )

    if use_numba_effective:
        # Prepare Numba-typed collections
        # These must be nb.typed.List/Dict for the Numba kernel
        _node_ids_list_nb = nb.typed.List(node_ids_list_py)
        _delay_lines_nodes_nb = nb.typed.Dict.empty(
            key_type=nb.types.unicode_type, value_type=nb.float32[::1]
        )
        _current_write_pos_nodes_nb = nb.typed.Dict.empty(
            key_type=nb.types.unicode_type, value_type=nb.int_
        )
        for node_id_py, dl_arr_py in delay_lines_nodes.items():
            _delay_lines_nodes_nb[node_id_py] = (
                dl_arr_py  # dl_arr_py is already np.float32[::1] compatible
            )
        for node_id_py, wp_py in current_write_pos_nodes.items():
            _current_write_pos_nodes_nb[node_id_py] = wp_py

    # Process audio in blocks
    for i in range(0, num_samples, block_size):
        start_idx = i
        end_idx = min(i + block_size, num_samples)
        current_block_len = end_idx - start_idx

        current_input_block = audio_data[start_idx:end_idx].astype(NUMERIC_DTYPE)
        # Pad if last block is smaller than block_size (kernels expect full block_size)
        if current_block_len < block_size:
            padding = np.zeros(block_size - current_block_len, dtype=NUMERIC_DTYPE)
            current_input_block = np.concatenate((current_input_block, padding))

        processed_block: np.ndarray
        block_rms: float

        if use_numba_effective:
            # Call Numba kernel
            # Ensure all arrays passed are of the correct Numba basic types (e.g. np.float32, np.int_)
            # and collections are Numba typed collections.
            processed_block, block_rms, updated_write_pos_nb = _process_block_numba(
                current_input_block,
                graph.input_gain,
                graph.output_gain,
                graph.chaos_level,
                _node_ids_list_nb,  # nb.typed.List
                node_gains_arr_py,
                node_delays_arr_py,
                conn_source_indices_py,
                conn_target_indices_py,
                conn_gains_arr_py,
                conn_delay_samples_arr_py,
                _delay_lines_nodes_nb,  # nb.typed.Dict
                _current_write_pos_nodes_nb,  # nb.typed.Dict
                block_size,  # Numba int
            )
            # Numba dicts passed to JIT functions are often modified in place.
            # We assume _current_write_pos_nodes_nb is updated in place by the JIT func.

        else:
            # Call NumPy kernel
            processed_block, block_rms, current_write_pos_nodes = _process_block_numpy(
                current_input_block,
                graph,  # Pass the whole graph object
                delay_lines_nodes,  # Python dict of np.arrays
                current_write_pos_nodes,  # Python dict of ints
                block_size,
                sample_rate,  # NumPy version might need sample_rate for internal calcs if not pre-converted
            )

        if enable_rms_watchdog:
            avg_rms, watchdog_gain = _rms_watchdog_update(
                block_rms,
                avg_rms,
                watchdog_attack_coeff,
                watchdog_release_coeff,
                watchdog_limit_threshold_rms,
                watchdog_max_reduction_db,
            )
            processed_block *= watchdog_gain
            # Additional hard clipping just in case, after gain reduction
            processed_block = np.clip(processed_block, -1.0, 1.0)

        output_audio[start_idx:end_idx] = processed_block[:current_block_len]

    # If there was significant delay, the tail might be cut off.
    # A more advanced implementation might fade out or process silence for max_total_delay_samples.
    # For now, we assume output is same length as input.

    return output_audio


class MFN:
    """
    Builder class for creating and applying Multi-Feedback Network (MFN) effects.

    Provides a fluent interface to define the MFN graph structure (nodes, connections)
    and parameters, then build an MFNGraph object and process audio through it.
    """

    def __init__(self):
        self._nodes: List[MFNNode] = []
        self._connections: List[MFNConnection] = []
        self._input_gain: float = 1.0
        self._output_gain: float = 1.0
        self._chaos_level: float = 0.0
        self._node_id_set: set[str] = set()  # For quick validation of node IDs

    def add_node(
        self,
        node_id: str,
        gain: float = 1.0,
        delay_s: float = 0.0,
        max_delay_s: float = 1.0,  # Default max delay buffer of 1s
        # Add other MFNNode parameters here if they become configurable
    ) -> "MFN":
        """Adds a node to the MFN graph configuration."""
        if node_id in self._node_id_set:
            raise ValueError(f"Node with id '{node_id}' already exists.")

        node = MFNNode(id=node_id, gain=gain, delay_s=delay_s, max_delay_s=max_delay_s)
        self._nodes.append(node)
        self._node_id_set.add(node_id)
        return self

    def add_connection(
        self,
        source_node_id: str,
        target_node_id: str,
        gain: float = 1.0,
        delay_s: float = 0.0,  # Connection-specific delay, currently not used in kernel
    ) -> "MFN":
        """Adds a connection between two nodes in the MFN graph configuration."""
        if source_node_id not in self._node_id_set:
            raise ValueError(f"Source node '{source_node_id}' does not exist.")
        if target_node_id not in self._node_id_set:
            raise ValueError(f"Target node '{target_node_id}' does not exist.")

        connection = MFNConnection(
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            gain=gain,
            delay_s=delay_s,
        )
        self._connections.append(connection)
        return self

    def set_input_gain(self, gain: float) -> "MFN":
        """Sets the global input gain for the MFN graph."""
        self._input_gain = gain
        return self

    def set_output_gain(self, gain: float) -> "MFN":
        """Sets the global output gain for the MFN graph."""
        self._output_gain = gain
        return self

    def set_chaos_level(self, level: float) -> "MFN":
        """Sets the chaos level (non-linearity) for the MFN graph."""
        if not (0.0 <= level <= 1.0):
            raise ValueError("Chaos level must be between 0.0 and 1.0.")
        self._chaos_level = level
        return self

    def build(self) -> MFNGraph:
        """
        Builds and returns the MFNGraph object from the current configuration.
        Performs final validation.
        """
        if not self._nodes:
            logger.warning("Building MFNGraph with no nodes.")

        # Additional validation for connections (already partially done in add_connection)
        for conn in self._connections:
            if conn.source_node_id not in self._node_id_set:
                raise ValueError(
                    f"Connection source node '{conn.source_node_id}' not found in defined nodes."
                )
            if conn.target_node_id not in self._node_id_set:
                raise ValueError(
                    f"Connection target node '{conn.target_node_id}' not found in defined nodes."
                )

        return MFNGraph(
            nodes=self._nodes,
            connections=self._connections,
            input_gain=self._input_gain,
            output_gain=self._output_gain,
            chaos_level=self._chaos_level,
        )

    def process(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        block_size: int = 256,
        use_numba: bool = True,
        enable_rms_watchdog: bool = True,
        watchdog_limit_threshold_rms: float = 0.85,
        watchdog_attack_coeff: float = 0.05,
        watchdog_release_coeff: float = 0.005,
        watchdog_max_reduction_db: float = -18.0,
    ) -> np.ndarray:
        """
        Builds the MFNGraph and processes the audio data through it using apply_feedback_network.
        """
        graph = self.build()
        return apply_feedback_network(  # Updated to apply_feedback_network
            audio_data=audio_data,
            graph=graph,
            sample_rate=sample_rate,
            block_size=block_size,
            use_numba=use_numba,
            enable_rms_watchdog=enable_rms_watchdog,
            watchdog_limit_threshold_rms=watchdog_limit_threshold_rms,
            watchdog_attack_coeff=watchdog_attack_coeff,
            watchdog_release_coeff=watchdog_release_coeff,
            watchdog_max_reduction_db=watchdog_max_reduction_db,
        )


# Example Usage (for testing, can be removed or moved to a test file):
# if __name__ == '__main__':
#     # Configure logging to see output
#     logging.basicConfig(level=logging.INFO)

#     sr = 44100
#     duration = 2.0
#     frequency = 440
#     # Create a simple sine wave as input
#     t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=NUMERIC_DTYPE)
#     test_signal = 0.5 * np.sin(2 * np.pi * frequency * t)

#     # Create an MFN graph
#     mfn_builder = MFN()
#     mfn_builder.add_node(node_id='node1', delay_s=0.1, gain=0.8, max_delay_s=0.2)
#     mfn_builder.add_node(node_id='node2', delay_s=0.15, gain=0.7, max_delay_s=0.3)
#     mfn_builder.add_connection(source_node_id='node1', target_node_id='node2', gain=0.5)
#     mfn_builder.add_connection(source_node_id='node2', target_node_id='node1', gain=-0.4)
#     mfn_builder.set_input_gain(0.9)
#     mfn_builder.set_output_gain(1.0)
#     mfn_builder.set_chaos_level(0.1)

#     # Process the audio
#     logger.info("Processing with NumPy...")
#     processed_audio_numpy = mfn_builder.process(test_signal.copy(), sr, use_numba=False)

#     if NB_AVAILABLE:
#         logger.info("Processing with Numba...")
#         processed_audio_numba = mfn_builder.process(test_signal.copy(), sr, use_numba=True)
#         # Basic check: np.allclose(processed_audio_numpy, processed_audio_numba)
#         # This might not be exactly true due to floating point subtleties but should be close.
#         if np.allclose(processed_audio_numpy, processed_audio_numba, atol=1e-6):
#             logger.info("NumPy and Numba outputs are close.")
#         else:
#             logger.warning("NumPy and Numba outputs differ significantly.")
#             # diff = np.abs(processed_audio_numpy - processed_audio_numba)
#             # logger.warning(f"Max difference: {np.max(diff)}")


#     # For actual use, you'd save or play processed_audio
#     # import soundfile as sf
#     # sf.write("mfn_output_numpy.wav", processed_audio_numpy, sr)
#     # if NB_AVAILABLE:
#     #     sf.write("mfn_output_numba.wav", processed_audio_numba, sr)
#     logger.info("MFN processing example finished.")
