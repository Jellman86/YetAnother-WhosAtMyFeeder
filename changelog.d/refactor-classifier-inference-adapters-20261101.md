- The TFLite, ONNX Runtime and OpenVINO model adapters, and the image preprocessing
  and output checks they share, now live in their own inference package behind one
  adapter contract. Classification results, native crash handling, label checksums
  and status reporting are unchanged.
