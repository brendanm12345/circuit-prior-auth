from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from concurrent.futures import ThreadPoolExecutor
import asyncio
import platform
import argparse
import time
import json
import re
import os
import shutil
import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from prompts import SYSTEM_PROMPT
from openai import OpenAI
from fastapi import WebSocket
from utils import get_web_element_rect, encode_image, extract_information, print_message, \
    get_pdf_retrieval_ans_from_assistant, clip_message_and_obs, get_current_url

import sys
print(sys.executable)


def setup_logger(folder_path):
    log_file_path = os.path.join(folder_path, 'agent.log')

    logger = logging.getLogger()
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    handler = logging.FileHandler(log_file_path)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def driver_config(headless=False, force_device_scale=False, download_dir='downloads'):
    options = webdriver.ChromeOptions()

    if force_device_scale:
        options.add_argument("--force-device-scale-factor=1")
    if headless:
        options.add_argument("--headless")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
    options.add_experimental_option(
        "prefs", {
            "download.default_directory": os.path.abspath(download_dir),
            "plugins.always_open_pdf_externally": False
        }
    )
    return options


def format_msg(it, init_msg, pdf_obs, warn_obs, web_img_b64, web_text):
    if it == 1:
        init_msg += f"I've provided the tag name of each element and the text it contains (if text exists). Note that <textarea> or <input> may be textbox, but not exactly. Please focus more on the screenshot and then refer to the textual information.\n{
            web_text}"
        init_msg_format = {
            'role': 'user',
            'content': [
                {'type': 'text', 'text': init_msg},
            ]
        }
        init_msg_format['content'].append({"type": "image_url",
                                           "image_url": {"url": f"data:image/png;base64,{web_img_b64}"}})
        return init_msg_format
    else:
        if not pdf_obs:
            curr_msg = {
                'role': 'user',
                'content': [
                    {'type': 'text',
                        'text': f"Observation:{warn_obs} please analyze the attached screenshot and give the Thought and Action. I've provided the tag name of each element and the text it contains (if text exists). Note that <textarea> or <input> may be textbox, but not exactly. Please focus more on the screenshot and then refer to the textual information.\n{web_text}"},
                    {
                        'type': 'image_url',
                        'image_url': {"url": f"data:image/png;base64,{web_img_b64}"}
                    }
                ]
            }
        else:
            curr_msg = {
                'role': 'user',
                'content': [
                    {'type': 'text',
                        'text': f"Observation: {pdf_obs} Please analyze the response given by Assistant, then consider whether to continue iterating or not. The screenshot of the current page is also attached, give the Thought and Action. I've provided the tag name of each element and the text it contains (if text exists). Note that <textarea> or <input> may be textbox, but not exactly. Please focus more on the screenshot and then refer to the textual information.\n{web_text}"},
                    {
                        'type': 'image_url',
                        'image_url': {"url": f"data:image/png;base64,{web_img_b64}"}
                    }
                ]
            }
        return curr_msg


def call_gpt4v_api(openai_client, messages, api_model, seed):
    retry_times = 0
    while True:
        try:
            logging.info('Calling gpt4v API...')
            openai_response = openai_client.chat.completions.create(
                model=api_model, messages=messages, max_tokens=1000, seed=seed
            )

            prompt_tokens = openai_response.usage.prompt_tokens
            completion_tokens = openai_response.usage.completion_tokens

            logging.info(
                f'Prompt Tokens: {prompt_tokens}; Completion Tokens: {completion_tokens}')

            gpt_call_error = False
            return prompt_tokens, completion_tokens, gpt_call_error, openai_response

        except Exception as e:
            logging.info(
                f'Error occurred, retrying. Error type: {type(e).__name__}')

            if type(e).__name__ == 'RateLimitError':
                time.sleep(10)

            elif type(e).__name__ == 'APIError':
                time.sleep(15)

            elif type(e).__name__ == 'InvalidRequestError':
                gpt_call_error = True
                return None, None, gpt_call_error, None

            else:
                gpt_call_error = True
                return None, None, gpt_call_error, None

        retry_times += 1
        if retry_times == 10:
            logging.info('Retrying too many times')
            return None, None, True, None


def exec_action_click(info, web_ele, driver_task):
    driver_task.execute_script(
        "arguments[0].setAttribute('target', '_self')", web_ele)
    web_ele.click()
    time.sleep(3)


def exec_action_type(info, web_ele, driver_task):
    warn_obs = ""
    type_content = info['content']

    ele_tag_name = web_ele.tag_name.lower()
    ele_type = web_ele.get_attribute("type")
    # outer_html = web_ele.get_attribute("outerHTML")
    if (ele_tag_name != 'input' and ele_tag_name != 'textarea') or (ele_tag_name == 'input' and ele_type not in ['text', 'search', 'password', 'email', 'tel']):
        warn_obs = f"note: The web element you're trying to type may not be a textbox, and its tag name is <{
            web_ele.tag_name}>, type is {ele_type}."
    try:
        # Doesn't always work to delete
        web_ele.clear()
        # Another way to delete
        if platform.system() == 'Darwin':
            web_ele.send_keys(Keys.COMMAND + "a")
        else:
            web_ele.send_keys(Keys.CONTROL + "a")
        web_ele.send_keys(" ")
        web_ele.send_keys(Keys.BACKSPACE)
    except:
        pass

    actions = ActionChains(driver_task)
    actions.click(web_ele).perform()
    actions.pause(1)

    # prevent space from scrolling the page
    try:
        driver_task.execute_script(
            """window.onkeydown = function(e) {if(e.keyCode == 32 && e.target.type != 'text' && e.target.type != 'textarea' && e.target.type != 'search') {e.preventDefault();}};""")
    except:
        pass

    actions.send_keys(type_content)
    actions.pause(2)

    actions.send_keys(Keys.ENTER)
    actions.perform()
    time.sleep(10)
    return warn_obs


def exec_action_scroll(info, web_eles, driver_task, window_height):
    scroll_ele_number = info['number']
    scroll_content = info['content']
    if scroll_ele_number == "WINDOW":
        if scroll_content == 'down':
            driver_task.execute_script(
                f"window.scrollBy(0, {window_height*2//3});")
        else:
            driver_task.execute_script(
                f"window.scrollBy(0, {-window_height*2//3});")
    else:
        scroll_ele_number = int(scroll_ele_number)
        web_ele = web_eles[scroll_ele_number]
        actions = ActionChains(driver_task)
        driver_task.execute_script("arguments[0].focus();", web_ele)
        if scroll_content == 'down':
            actions.key_down(Keys.ALT).send_keys(
                Keys.ARROW_DOWN).key_up(Keys.ALT).perform()
        else:
            actions.key_down(Keys.ALT).send_keys(
                Keys.ARROW_UP).key_up(Keys.ALT).perform()
    time.sleep(3)


# async def run_browser_agent(
#         websocket: WebSocket,
#         task,
#         headless=True,
#         force_device_scale=False,
#         window_width=1024,
#         window_height=768,
#         fix_box_color=True,
#         output_dir='results',
#         seed=None,
#         max_iter=5,
#         api_model='gpt-4-vision-preview',
#         max_attached_imgs=1,
#         temperature=1.0,
#         download_dir='downloads',
#         print_url=True):
#     # OpenAI client
#     client = OpenAI()
#     options = driver_config(headless, force_device_scale, download_dir)

#     # Save Result file
#     current_time = time.strftime("%Y%m%d_%H_%M_%S", time.localtime())
#     result_dir = os.path.join(output_dir, current_time)
#     os.makedirs(result_dir, exist_ok=True)

#     print('task:', task)
#     try:
#         task_dir = os.path.join(result_dir, 'task{}'.format(task["id"]))
#         os.makedirs(task_dir, exist_ok=True)
#         setup_logger(task_dir)
#         logging.info(f'########## TASK{task["id"]} ##########')

#         driver_task = webdriver.Chrome(options=options)
#         driver_task.set_window_size(window_width, window_height)
#         driver_task.get(task['web'])
#         try:
#             driver_task.find_element(By.TAG_NAME, 'body').click()
#         except:
#             pass
#         # prevent space from scrolling the page
#         driver_task.execute_script(
#             """window.onkeydown = function(e) {if(e.keyCode == 32 && e.target.type != 'text' && e.target.type != 'textarea') {e.preventDefault();}};""")
#         time.sleep(5)

#         # clear download files
#         for filename in os.listdir(download_dir):
#             file_path = os.path.join(download_dir, filename)
#             if os.path.isfile(file_path):
#                 os.remove(file_path)

#         download_files = []

#         fail_obs, pdf_obs, warn_obs = "", "", ""
#         pattern = r'Thought:|Action:|Observation:'

#         messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]
#         obs_prompt = "Observation: please analyze the attached screenshot and give the Thought and Action. "
#         init_msg = f"""Now given a task: {
#             task['ques']}  Please interact with https://www.example.com and get the answer. \n"""
#         init_msg = init_msg.replace('https://www.example.com', task['web'])
#         init_msg = init_msg + obs_prompt

#         it, accumulate_prompt_token, accumulate_completion_token = 0, 0, 0

#         while it < max_iter:
#             logging.info(f'Iter: {it}')
#             it += 1
#             if not fail_obs:
#                 # try to make bounding boxes
#                 try:
#                     rects, web_eles, web_eles_text = get_web_element_rect(
#                         driver_task, fix_color=fix_box_color)
#                 except Exception as e:
#                     logging.error('Driver error when adding set-of-mark.')
#                     logging.error(e)
#                     break

#                 # take screenshot
#                 img_path = os.path.join(
#                     task_dir, 'screenshot{}.png'.format(it))
#                 driver_task.save_screenshot(img_path)
#                 b64_img = encode_image(img_path)

#                 # format msg
#                 curr_msg = format_msg(
#                     it, init_msg, pdf_obs, warn_obs, b64_img, web_eles_text)
#                 messages.append(curr_msg)
#             else:
#                 curr_msg = {
#                     'role': 'user',
#                     'content': fail_obs
#                 }
#                 messages.append(curr_msg)

#             # Clip messages, too many attached images may cause confusion
#             messages = clip_message_and_obs(
#                 messages, max_attached_imgs)

#             # Call GPT-4v API
#             prompt_tokens, completion_tokens, gpt_call_error, openai_response = call_gpt4v_api(
#                 client, messages, api_model, seed)
#             if gpt_call_error:
#                 break
#             else:
#                 accumulate_prompt_token += prompt_tokens
#                 accumulate_completion_token += completion_tokens
#                 logging.info(
#                     f'Accumulate Prompt Tokens: {accumulate_prompt_token}; Accumulate Completion Tokens: {accumulate_completion_token}')
#                 logging.info('API call complete...')
#             gpt_4v_res = openai_response.choices[0].message.content
#             messages.append({'role': 'assistant', 'content': gpt_4v_res})

#             # remove the rects on the website
#             if rects:
#                 logging.info(f"Num of interactive elements: {len(rects)}")
#                 for rect_ele in rects:
#                     driver_task.execute_script(
#                         "arguments[0].remove()", rect_ele)
#                 rects = []

#             # extract action info
#             try:
#                 assert 'Thought:' in gpt_4v_res and 'Action:' in gpt_4v_res
#             except AssertionError as e:
#                 logging.error(e)
#                 fail_obs = "Format ERROR: Both 'Thought' and 'Action' should be included in your reply."
#                 continue

#             # bot_thought = re.split(pattern, gpt_4v_res)[1].strip()
#             chosen_action = re.split(pattern, gpt_4v_res)[2].strip()
#             print(chosen_action)
#             action_key, info = extract_information(chosen_action)
#             await websocket.send_json({
#                 "status": "action_update",
#                 "details": f"Executing {chosen_action} on element {info}"
#             })

#             fail_obs, pdf_obs, warn_obs = "", "", ""
#             # execute action
#             try:
#                 window_handle_task = driver_task.current_window_handle
#                 driver_task.switch_to.window(window_handle_task)

#                 if action_key == 'click':
#                     click_ele_number = int(info[0])
#                     web_ele = web_eles[click_ele_number]
#                     ele_tag_name = web_ele.tag_name.lower()
#                     ele_type = web_ele.get_attribute("type")
#                     exec_action_click(info, web_ele, driver_task)

#                     current_files = sorted(os.listdir(download_dir))
#                     if current_files != download_files:
#                         # wait for download finish
#                         time.sleep(10)
#                         current_files = sorted(os.listdir(download_dir))

#                         current_download_file = [
#                             pdf_file for pdf_file in current_files if pdf_file not in download_files and pdf_file.endswith('.pdf')]
#                         if current_download_file:
#                             pdf_file = current_download_file[0]
#                             pdf_obs = get_pdf_retrieval_ans_from_assistant(
#                                 client, os.path.join(download_dir, pdf_file), task['ques'])
#                             shutil.copy(os.path.join(
#                                 download_dir, pdf_file), task_dir)
#                             pdf_obs = "You downloaded a PDF file, I ask the Assistant API to answer the task based on the PDF file and get the following response: " + pdf_obs
#                         download_files = current_files

#                     if ele_tag_name == 'button' and ele_type == 'submit':
#                         time.sleep(10)

#                 elif action_key == 'wait':
#                     time.sleep(5)

#                 elif action_key == 'type':
#                     type_ele_number = int(info['number'])
#                     web_ele = web_eles[type_ele_number]

#                     warn_obs = exec_action_type(info, web_ele, driver_task)
#                     if 'wolfram' in task['web']:
#                         time.sleep(5)

#                 elif action_key == 'scroll':
#                     exec_action_scroll(
#                         info, web_eles, driver_task, window_height)

#                 elif action_key == 'goback':
#                     driver_task.back()
#                     time.sleep(2)

#                 elif action_key == 'google':
#                     driver_task.get('https://www.google.com/')
#                     time.sleep(2)

#                 elif action_key == 'answer':
#                     logging.info(info['content'])
#                     logging.info('Finished!')
#                     break

#                 else:
#                     raise NotImplementedError
#                 fail_obs = ""
#             except Exception as e:
#                 logging.error('driver error info:')
#                 logging.error(e)
#                 await websocket.send_json({
#                     "status": "error",
#                     "message": str(e)
#                 })
#                 if 'element click intercepted' not in str(e):
#                     fail_obs = "The action you have chosen cannot be exected. Please double-check if you have selected the wrong Numerical Label or Action or Action format. Then provide the revised Thought and Action."
#                 else:
#                     fail_obs = ""
#                 time.sleep(2)

#             finally:
#                 print_message(messages, task_dir)
#                 if print_url:
#                     final_url = driver_task.current_url
#                 driver_task.quit()
#                 logging.info(
#                     f'Total cost: {accumulate_prompt_token / 1000 * 0.01 + accumulate_completion_token / 1000 * 0.03}')

#     except Exception as e:
#         await websocket.send_json({"status": "error", "message": str(e)})
#     finally:
#         await websocket.close()


# async def run_browser_agent(websocket: WebSocket, tasks):
#     print('Running tasks...')
#     print('tasks:', tasks)  # Debugging print

#     try:
#         for task in tasks:
#             # Simulate task processing with updates
#             await asyncio.sleep(1)  # Simulate time-consuming task
#             await websocket.send_json({"status": "processing", "details": f"Processing task {task['id']}"})
#             # Simulate actions taken during the task
#             actions = [0, 7, 5, 9, 1]
#             for action in actions:
#                 print(f"Click [{action}]")
#                 await asyncio.sleep(0.5)  # Simulate action delay
#                 await websocket.send_json({"status": "action", "details": f"Click [{action}]"})

#         # Send a completion message at the end of all tasks
#         await websocket.send_json({"status": "completed", "result": "All tasks processed successfully"})
#     except Exception as e:
#         await websocket.send_json({"status": "error", "message": str(e)})
#     finally:
#         await websocket.close()  # Ensure the connection is closed after all tasks


async def perform_action_and_notify(websocket, driver, action_details):
    loop = asyncio.get_running_loop()

    try:
        if action_details['type'] == 'check_text':
            assert action_details['text'] in driver.page_source
            print(f"Text '{action_details['text']}' found on the page.")
            await websocket.send_json({"status": "action_completed", "details": f"Text '{action_details['text']}' found on the page."})
            print("Web socket message sent.")
            time.sleep(3)

        elif action_details['type'] == 'take_screenshot':
            driver.save_screenshot(action_details['filename'])
            print(f"Screenshot taken and saved as '{
                  action_details['filename']}'.")
            await websocket.send_json({"status": "action_completed", "details": f"Screenshot taken and saved as '{action_details['filename']}'."})
            print("Web socket message sent.")
            time.sleep(3)

        elif action_details['type'] == 'click_link':
            link = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (By.PARTIAL_LINK_TEXT, action_details['link_text']))
            )
            link.click()
            print(f"Clicked on link with text: {action_details['link_text']}")
            await websocket.send_json({"status": "action_completed", "details": f"Clicked on link with text: {action_details['link_text']}"})
            print("Web socket message sent.")
            time.sleep(3)

    except Exception as e:
        await websocket.send_json({"status": "error", "message": str(e)})
        return


async def run_browser_agent(websocket, task):
    driver = webdriver.Chrome()  # Setup WebDriver
    driver.get(task['web'])  # Load the page

    # Define actions specific to example.com
    actions = [
        {'type': 'check_text', 'text': 'Example Domain'},
        {'type': 'take_screenshot', 'filename': 'example_com_screenshot.png'},
        {'type': 'click_link', 'link_text': 'More information...'}
    ]

    for action in actions:
        await perform_action_and_notify(websocket, driver, action)
        print(f"Action completed: {action}")

    driver.quit()


# Setup WebSocket and Task
# Assume websocket is already an established WebSocket connection
# task is a dictionary containing necessary task details
