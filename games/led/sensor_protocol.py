"""Incremental parser for floor sensor frames.

The controller continuously emits ``0xFC, payload_length, payload``. Serial
reads may split a frame or contain several frames, so callers must retain the
returned remainder and prepend it to the next read.
"""


FRAME_HEADER = 0xFC


def extract_frames(data, expected_payload_size):
    """Return ``(payloads, remainder, dropped_bytes)`` from a byte stream.

    Only frames whose declared size matches the COM port's configured tile
    range are accepted. Invalid headers/lengths are skipped one byte at a time
    so the parser can resynchronize on the next ``0xFC``.
    """
    buffer = bytearray(data)
    payloads = []
    dropped = 0

    while buffer:
        try:
            header_index = buffer.index(FRAME_HEADER)
        except ValueError:
            dropped += len(buffer)
            buffer.clear()
            break

        if header_index:
            dropped += header_index
            del buffer[:header_index]

        if len(buffer) < 2:
            break

        payload_size = buffer[1]
        if payload_size != expected_payload_size:
            dropped += 1
            del buffer[0]
            continue

        frame_size = payload_size + 2
        if len(buffer) < frame_size:
            break

        payloads.append(bytes(buffer[2:frame_size]))
        del buffer[:frame_size]

    return payloads, bytes(buffer), dropped


def reversed_position_values(payload, start_index, total_positions):
    """Decode controller payload order into validated logical position indices."""
    payload_size = len(payload)
    for offset, value in enumerate(payload):
        position_index = start_index + payload_size - 1 - offset
        if not 0 <= position_index < total_positions:
            raise IndexError(
                f"sensor position {position_index} outside 0..{total_positions - 1}"
            )
        yield position_index, value
