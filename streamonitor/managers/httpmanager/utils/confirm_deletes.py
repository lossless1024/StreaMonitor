from parameters import WEB_CONFIRM_DELETES


def confirm_deletes(user_agent: str):
    ua = user_agent.lower()
    mobile_strings = ['android', 'iphone', 'ipad', 'mobile']
    if WEB_CONFIRM_DELETES and WEB_CONFIRM_DELETES != "MOBILE":
        return True
    elif WEB_CONFIRM_DELETES:
        return any(mobile in ua for mobile in mobile_strings)
    else:
        return False