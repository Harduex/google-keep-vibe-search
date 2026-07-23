# Local LLM Tool Calling and LM Studio Hijacking

**Problem**: When using `Instruct` models (like Meta-Llama-3.1-8B-Instruct) via LM Studio locally, asking the model for plain text or JSON output often fails. LM Studio detects the instruct template and automatically injects tool-calling tokens (`<|python_tag|>`), causing the model to hallucinate fake tool calls (e.g., `{"name": "summarize_notes"}`).
**Root Cause**: Conflict between our plain-text / `json_object` format requests and LM Studio forcing the model into an agentic "Tool Use API" mode behind the scenes.
**Solution**: Stop fighting the model's reflex. Use LiteLLM's `complete_with_tools` and pass an explicit tool definition (e.g., `generate_tag`) with `tool_choice="required"`. By giving the model a real tool schema, it effortlessly outputs the exact structured data needed without negative constraint collapse or hallucinated tools.
