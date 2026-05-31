# VN Asset QA Checklist

## File QA
- File exists and is non-empty.
- Image/audio extension matches asset type.
- Image dimensions suit target display or are transform-safe.
- Audio is playable and short/loopable as intended.

## Visual / Audio QA
- No unwanted readable text, watermark, logo, or UI artifact.
- No unwanted humans in background/prop-only assets.
- Character identity and outfit match canon.
- Prop is readable at VN display scale.

## Promotion Gate
- Candidate has a passing file QA report.
- Owner explicitly approved the candidate.
- Promotion updates manifest and source metadata.
- Ren'Py asset refs and lint pass after integration.
