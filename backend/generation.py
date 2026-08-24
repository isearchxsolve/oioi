import asyncio


async def batch_generate(prompts):
    # Simulate concurrent generation
    results = []
    for p in prompts:
        results.append({'prompt': p, 'status': 'ok'})
    return results


async def generate_video_with_frames(prompt, first_frame, last_frame):
    return {'prompt': prompt, 'first_frame': first_frame, 'last_frame': last_frame, 'status': 'ok'}


async def generate_with_reference(prompt, reference_image, mode='style'):
    return {'prompt': prompt, 'reference_image': reference_image, 'mode': mode, 'status': 'ok'}
