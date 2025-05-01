def get_recording_query_params(sort_by_size, current_video):
    params = []
    if(sort_by_size):
        params.append("sorted=True")
    if(current_video is not None):
        params.append(f"play_video={current_video}")
    query_param = f"?{'&'.join(params)}" if len(params) > 0 else ""
    return query_param