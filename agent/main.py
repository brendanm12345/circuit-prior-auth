# RUN: uvicorn main:app --reload
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from fastapi import FastAPI, Request, WebSocket
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from prompts import SYSTEM_PROMPT
from openai import OpenAI
from fastapi import WebSocket
from concurrent.futures import ThreadPoolExecutor
from utils import get_web_element_rect, encode_image, extract_information, print_message, \
    get_pdf_retrieval_ans_from_assistant, clip_message_and_obs
import sys
import asyncio
import platform
import time
import json
import re
import os
import shutil
import logging
import websockets
print(sys.executable)


app = FastAPI()
client = OpenAI()
executor = ThreadPoolExecutor(max_workers=4)


async def run_in_executor(func, *args):
    """ Utility function to run blocking tasks in an executor """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, func, *args)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    body = await request.body()
    response = await call_next(request)
    return response

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.post("/")
async def root():
    return {"message": "Hello World"}


@app.websocket("/ws/agent")
async def websocket_agent(websocket: WebSocket):
    await websocket.accept()  # Accept the WebSocket connection
    try:
        while True:
            task = await websocket.receive_json()
            print("Received task:", task)
            # Run browser agent in the background, allowing the WebSocket to handle other messages
            await run_browser_agent(websocket, task)
    except websockets.exceptions.ConnectionClosedError as e:
        # Log error and potentially initiate a reconnection
        print(f"WebSocket closed with error: {e}")
        logging.error(f"Error in WebSocket communication: {str(e)}")
        await websocket.send_json({"status": "error", "message": str(e)})
    finally:
        if not websocket.client_state.value == "DISCONNECTED":
            await websocket.close()


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


async def call_gpt4v_api(openai_client, messages, api_model, seed):
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
                await asyncio.sleep(10)

            elif type(e).__name__ == 'APIError':
                await asyncio.sleep(15)

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


async def exec_action_click(info, web_ele, driver_task):
    driver_task.execute_script(
        "arguments[0].setAttribute('target', '_self')", web_ele)
    await run_in_executor(web_ele.click)
    await asyncio.sleep(3)


async def exec_action_type(info, web_ele, driver_task):
    warn_obs = ""
    type_content = info['content']

    ele_tag_name = web_ele.tag_name.lower()
    ele_type = web_ele.get_attribute("type")
    if (ele_tag_name != 'input' and ele_tag_name != 'textarea') or \
       (ele_tag_name == 'input' and ele_type not in ['text', 'search', 'password', 'email', 'tel']):
        warn_obs = f"Note: The web element you're trying to type may not be a textbox. Tag name: <{
            ele_tag_name}>, type: {ele_type}."

    try:
        # Clear the element before typing; involves clicking and sending keys
        actions = ActionChains(driver_task)
        actions.click(web_ele)
        if platform.system() == 'Darwin':
            actions.send_keys(Keys.COMMAND + "a")
        else:
            actions.send_keys(Keys.CONTROL + "a")
        actions.send_keys(Keys.BACKSPACE)
        await run_in_executor(actions.perform)

        # Setting up to type the provided content
        actions.reset_actions()  # Reset the previous actions
        actions.send_keys(type_content)
        actions.send_keys(Keys.ENTER)
        await run_in_executor(actions.perform)
    except Exception as e:
        warn_obs += f" Error during typing action: {str(e)}"

    # Script to prevent space from scrolling the page
    script_to_prevent_scrolling = """
    window.onkeydown = function(e) {
        if (e.keyCode == 32 && e.target.type != 'text' && e.target.type != 'textarea' && e.target.type != 'search') {
            e.preventDefault();
        }
    };"""
    await run_in_executor(driver_task.execute_script, script_to_prevent_scrolling)

    await asyncio.sleep(10)  # Delays for UI to update, if necessary
    print("Done sleeping after typing.")
    return warn_obs


async def exec_action_scroll(info, web_eles, driver_task, window_height):
    scroll_ele_number = info['number']
    scroll_content = info['content']

    if scroll_ele_number == "WINDOW":
        script = f"window.scrollBy(0, {
            window_height*2//3 if scroll_content == 'down' else -window_height*2//3});"
        await run_in_executor(driver_task.execute_script, script)
    else:
        scroll_ele_number = int(scroll_ele_number)
        web_ele = web_eles[scroll_ele_number]
        actions = ActionChains(driver_task)
        await run_in_executor(driver_task.execute_script, "arguments[0].focus();", web_ele)
        if scroll_content == 'down':
            await run_in_executor(actions.key_down, Keys.ALT)
            await run_in_executor(actions.send_keys, Keys.ARROW_DOWN)
            await run_in_executor(actions.key_up, Keys.ALT)
            await run_in_executor(actions.perform)
        else:
            await run_in_executor(actions.key_down, Keys.ALT)
            await run_in_executor(actions.send_keys, Keys.ARROW_UP)
            await run_in_executor(actions.key_up, Keys.ALT)
            await run_in_executor(actions.perform)

    await asyncio.sleep(3)  # Delays for UI to update, if necessary


async def run_browser_agent(
        websocket: WebSocket,
        task,
        headless=True,
        force_device_scale=False,
        window_width=1024,
        window_height=768,
        fix_box_color=True,
        output_dir='results',
        seed=None,
        max_iter=5,
        api_model='gpt-4-vision-preview',
        max_attached_imgs=1,
        temperature=1.0,
        download_dir='downloads',
        print_url=True):
    # OpenAI client
    client = OpenAI()
    options = driver_config(headless, force_device_scale, download_dir)

    # Save Result file
    current_time = time.strftime("%Y%m%d_%H_%M_%S", time.localtime())
    result_dir = os.path.join(output_dir, current_time)
    os.makedirs(result_dir, exist_ok=True)

    try:
        task_dir = os.path.join(result_dir, 'task{}'.format(task["id"]))
        os.makedirs(task_dir, exist_ok=True)
        setup_logger(task_dir)
        logging.info(f'########## TASK{task["id"]} ##########')

        await websocket.send_json({"status": "starting", "details": f"Opening browser..."})
        driver = webdriver.Chrome(options=options)
        driver.set_window_size(window_width, window_height)
        driver.get(task['web'])
        try:
            driver.find_element(By.TAG_NAME, 'body').click()
        except:
            pass
        # prevent space from scrolling the page
        driver.execute_script(
            """window.onkeydown = function(e) {if(e.keyCode == 32 && e.target.type != 'text' && e.target.type != 'textarea') {e.preventDefault();}};""")
        await asyncio.sleep(2)

        # clear download files
        for filename in os.listdir(download_dir):
            file_path = os.path.join(download_dir, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)

        download_files = []

        fail_obs, pdf_obs, warn_obs = "", "", ""
        pattern = r'Thought:|Action:|Observation:|Description:'

        messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]
        obs_prompt = "Observation: please analyze the attached screenshot and give the Thought, Action, and Description. "
        init_msg = f"""Now given a task: {
            task['ques']}  Please interact with https://www.example.com and get the answer. \n"""
        init_msg = init_msg.replace('https://www.example.com', task['web'])
        init_msg = init_msg + obs_prompt

        await asyncio.sleep(2)

        it, accumulate_prompt_token, accumulate_completion_token = 0, 0, 0

        while it < max_iter:
            logging.info(f'Iter: {it}')
            it += 1
            if not fail_obs:
                # try to make bounding boxes
                try:
                    rects, web_eles, web_eles_text = get_web_element_rect(
                        driver, fix_color=fix_box_color)
                except Exception as e:
                    logging.error('Driver error when adding set-of-mark.')
                    logging.error(e)
                    break

                # take screenshot
                img_path = os.path.join(
                    task_dir, 'screenshot{}.png'.format(it))
                driver.save_screenshot(img_path)
                b64_img = encode_image(img_path)

                # format msg
                curr_msg = format_msg(
                    it, init_msg, pdf_obs, warn_obs, b64_img, web_eles_text)
                messages.append(curr_msg)
            else:
                curr_msg = {
                    'role': 'user',
                    'content': fail_obs
                }
                messages.append(curr_msg)

            # Clip messages, too many attached images may cause confusion
            messages = clip_message_and_obs(
                messages, max_attached_imgs)

            # Call GPT-4v API
            prompt_tokens, completion_tokens, gpt_call_error, openai_response = await call_gpt4v_api(
                client, messages, api_model, seed)
            if gpt_call_error:
                break
            else:
                accumulate_prompt_token += prompt_tokens
                accumulate_completion_token += completion_tokens
                logging.info(
                    f'Accumulate Prompt Tokens: {accumulate_prompt_token}; Accumulate Completion Tokens: {accumulate_completion_token}')
                logging.info('API call complete...')
            gpt_4v_res = openai_response.choices[0].message.content
            messages.append({'role': 'assistant', 'content': gpt_4v_res})

            # remove the rects on the website
            if rects:
                logging.info(f"Num of interactive elements: {len(rects)}")
                for rect_ele in rects:
                    driver.execute_script(
                        "arguments[0].remove()", rect_ele)
                rects = []

            # extract action info
            try:
                assert 'Thought:' in gpt_4v_res and 'Action:' in gpt_4v_res and 'Description:' in gpt_4v_res
            except AssertionError as e:
                logging.error(e)
                fail_obs = "Format ERROR: 'Thought', 'Action' and 'Description' should be included in your reply."
                continue

            components = re.split(pattern, gpt_4v_res)
            bot_thought = components[1].strip()
            chosen_action = components[2].strip()
            description = components[3].strip()
            action_key, info = extract_information(chosen_action)
            print(description)
            await websocket.send_json({
                "status": "action_update",
                "details": description
            })
            await asyncio.sleep(.2)

            fail_obs, pdf_obs, warn_obs = "", "", ""
            # execute action
            try:
                window_handle_task = driver.current_window_handle
                driver.switch_to.window(window_handle_task)

                if action_key == 'click':
                    print(f"Clicking on element {web_ele}")
                    click_ele_number = int(info[0])
                    web_ele = web_eles[click_ele_number]
                    ele_tag_name = web_ele.tag_name.lower()
                    ele_type = web_ele.get_attribute("type")
                    print(f"Exec clicking on element {web_ele}")
                    await exec_action_click(info, web_ele, driver)

                    current_files = sorted(os.listdir(download_dir))
                    if current_files != download_files:
                        # wait for download finish
                        await asyncio.sleep(10)
                        current_files = sorted(os.listdir(download_dir))

                        current_download_file = [
                            pdf_file for pdf_file in current_files if pdf_file not in download_files and pdf_file.endswith('.pdf')]
                        if current_download_file:
                            pdf_file = current_download_file[0]
                            pdf_obs = get_pdf_retrieval_ans_from_assistant(
                                client, os.path.join(download_dir, pdf_file), task['ques'])
                            shutil.copy(os.path.join(
                                download_dir, pdf_file), task_dir)
                            pdf_obs = "You downloaded a PDF file, I ask the Assistant API to answer the task based on the PDF file and get the following response: " + pdf_obs
                        download_files = current_files

                    if ele_tag_name == 'button' and ele_type == 'submit':
                        await asyncio.sleep(10)

                elif action_key == 'wait':
                    await asyncio.sleep(5)

                elif action_key == 'type':
                    type_ele_number = int(info['number'])
                    web_ele = web_eles[type_ele_number]

                    warn_obs = await exec_action_type(info, web_ele, driver)
                    if 'wolfram' in task['web']:
                        await asyncio.sleep(5)

                elif action_key == 'scroll':
                    await exec_action_scroll(
                        info, web_eles, driver, window_height)

                elif action_key == 'goback':
                    driver.back()
                    await asyncio.sleep(2)

                elif action_key == 'google':
                    driver.get('https://www.google.com/')
                    await asyncio.sleep(2)

                elif action_key == 'answer':
                    logging.info(info['content'])
                    logging.info('Finished!')
                    break

                else:
                    raise NotImplementedError
                fail_obs = ""
            except Exception as e:
                logging.error('driver error info:')
                logging.error(e)
                await websocket.send_json({
                    "status": "error",
                    "message": str(e)
                })
                if 'element click intercepted' not in str(e):
                    fail_obs = "The action you have chosen cannot be exected. Please double-check if you have selected the wrong Numerical Label or Action or Action format. Then provide the revised Thought and Action."
                else:
                    fail_obs = ""
                await asyncio.sleep(2)

        print_message(messages, task_dir)
        if print_url:
            final_url = driver.current_url
        logging.info(
            f'Total cost: {accumulate_prompt_token / 1000 * 0.01 + accumulate_completion_token / 1000 * 0.03}')
        await websocket.send_json({
            "status": "task_completed",
            "details": {
                "message": info['content'],
                "url": final_url
            }
        })

    except Exception as e:
        await websocket.send_json({"status": "error", "message": str(e)})
