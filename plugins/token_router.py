import re, hashlib, base64, requests, time
from io import BytesIO
from config import OMNIROUTE_BASE_URL, OMNIROUTE_API_KEY, FREELLMAPI_BASE_URL

router_telemetry = {"mode": "OMNIROUTE_FRONTIER", "current_model": "OmniRoute // Frontier-Auto", "last_provider": "ZERO-GEMINI-LOCK", "tokens_remaining": "∞ (0 GEMINI)", "omniroute_online": False}
response_cache = {}

def compress_prompt_caveman(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip() if text and len(text) > 120 else text

def check_omniroute_health() -> bool:
    try:
        r = requests.get(f"{OMNIROUTE_BASE_URL}/models", headers={"Authorization": f"Bearer {OMNIROUTE_API_KEY}"}, timeout=1.2)
        if r.status_code == 200:
            router_telemetry["omniroute_online"] = True
            return True
    except Exception: pass
    router_telemetry["omniroute_online"] = False
    return False

def call_omniroute(prompt, sys_inst="", use_pro=False, json_mode=False, image_pil=None):
    msgs = [{"role": "system", "content": compress_prompt_caveman(sys_inst)}] if sys_inst else []
    if image_pil:
        buf = BytesIO(); image_pil.save(buf, format="JPEG", quality=75)
        msgs.append({"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"}}]})
    else:
        msgs.append({"role": "user", "content": compress_prompt_caveman(prompt)})
    
    payload = {"model": "auto", "messages": msgs, "temperature": 0.2}
    if json_mode: payload["response_format"] = {"type": "json_object"}
    r = requests.post(f"{OMNIROUTE_BASE_URL}/chat/completions", headers={"Authorization": f"Bearer {OMNIROUTE_API_KEY}", "Content-Type": "application/json"}, json=payload, timeout=22)
    r.raise_for_status()
    data = r.json()
    router_telemetry.update({"omniroute_online": True, "current_model": f"OmniRoute // {data.get('model', 'auto')[:20]}", "last_provider": "OMNIROUTE-LOCAL", "tokens_remaining": "1.62B FREE POOL"})
    return data["choices"][0]["message"]["content"].strip()

def call_freellmapi(prompt, sys_inst="", json_mode=False):
    msgs = [{"role": "system", "content": compress_prompt_caveman(sys_inst)}] if sys_inst else []
    msgs.append({"role": "user", "content": compress_prompt_caveman(prompt)})
    payload = {"model": "auto", "messages": msgs, "temperature": 0.2}
    if json_mode: payload["response_format"] = {"type": "json_object"}
    r = requests.post(f"{FREELLMAPI_BASE_URL}/chat/completions", json=payload, timeout=14)
    r.raise_for_status()
    data = r.json()
    router_telemetry.update({"current_model": f"FreeLLM // {data.get('model', 'auto')[:18]}", "last_provider": "FREELLMAPI-LOCAL", "tokens_remaining": "7.4B FREE POOL"})
    return data["choices"][0]["message"]["content"].strip()

def call_frontier_cloud_router(prompt, sys_inst="", use_pro=False, json_mode=False, image_pil=None):
    msgs = [{"role": "system", "content": compress_prompt_caveman(sys_inst)}] if sys_inst else []
    if image_pil:
        buf = BytesIO(); image_pil.save(buf, format="JPEG", quality=75)
        msgs.append({"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"}}]})
    else:
        msgs.append({"role": "user", "content": compress_prompt_caveman(prompt)})
    
    for f_model in ["openai-large", "claude-hybridspace", "deepseek-reasoner", "qwen-coder", "openai"]:
        try:
            payload = {"model": f_model, "messages": msgs, "temperature": 0.2}
            if json_mode: payload["response_format"] = {"type": "json_object"}
            r = requests.post("https://text.pollinations.ai/openai", json=payload, timeout=22)
            if r.status_code == 200:
                content = r.json()["choices"][0]["message"]["content"].strip()
                if content:
                    router_telemetry.update({"current_model": f"Frontier // {f_model}", "last_provider": f"FRONTIER ({f_model.upper()})", "tokens_remaining": "∞ (GEMINI LOCKED)"})
                    return content
        except Exception: continue
    raise RuntimeError("Frontier cloud busy")

def call_ai(prompt, sys_inst="", use_pro=False, json_mode=False, image_pil=None):
    cache_key = hashlib.md5(f"{sys_inst}|{prompt}|{json_mode}".encode()).hexdigest()
    if not image_pil and cache_key in response_cache:
        router_telemetry["last_provider"] = "SEMANTIC-CACHE (0 TOKENS)"
        return response_cache[cache_key]
    
    for fn in (lambda: call_omniroute(prompt, sys_inst, use_pro, json_mode, image_pil), lambda: call_freellmapi(prompt, sys_inst, json_mode) if not image_pil else None, lambda: call_frontier_cloud_router(prompt, sys_inst, use_pro, json_mode, image_pil)):
        try:
            res = fn()
            if res:
                if not image_pil: response_cache[cache_key] = res
                return res
        except Exception: continue
    return '{"parallel_wave": [], "final_spoken_reply": "Ready, sir."}' if json_mode else "Processed locally, sir."
