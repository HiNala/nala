import asyncio, os, time, sys
sys.path.insert(0, 'python-orchestrator')
# Load API key from environment or .env — never hardcode keys here
# Set OPENAI_API_KEY in your shell or project .env before running

async def test():
    import openai, httpx
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set in environment")
        return
    client = openai.AsyncOpenAI(
        api_key=api_key,
        timeout=httpx.Timeout(connect=15.0, read=90.0, write=30.0, pool=10.0)
    )
    t0 = time.monotonic()
    print("Sending request...")
    stream = await client.chat.completions.create(
        model='gpt-4o',
        messages=[{'role':'user','content':'say hello in one word'}],
        max_tokens=10,
        stream=True
    )
    first = True
    result = []
    async for event in stream:
        delta = event.choices[0].delta if event.choices else None
        if delta and delta.content:
            if first:
                print(f'First token at {time.monotonic()-t0:.1f}s')
                first = False
            result.append(delta.content)
    joined = "".join(result)
    print(f'Done at {time.monotonic()-t0:.1f}s: {joined!r}')

asyncio.run(test())
