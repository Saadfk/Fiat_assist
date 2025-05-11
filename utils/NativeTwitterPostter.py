import pychrome
import time


def attach_to_tab(browser, target_title="Home / X"):
    tabs = browser.list_tab()
    print(f"Found {len(tabs)} tabs.")
    for tab in tabs:
        try:
            tab.start()
            tab.call_method("Runtime.enable")
            result = tab.call_method("Runtime.evaluate", expression="document.title")
            title = result.get("result", {}).get("value", "")
            print(f"Tab ID {tab.id} title: {title}")
            if target_title in title:
                print(f"Automatically selecting tab with title: {title}")
                return tab
            tab.stop()
        except Exception as e:
            print(f"Error with tab ID {tab.id}: {e}")
            try:
                tab.stop()
            except Exception:
                pass
    raise RuntimeError(f"Tab titled '{target_title}' not found.")


def click_element_at(tab, manual_coords, element_name="element"):
    x = manual_coords["x"]
    y = manual_coords["y"]
    print(f"Using manually provided {element_name} center: x={x}, y={y}")
    try:
        tab.call_method("Input.dispatchMouseEvent",
                        type="mousePressed",
                        x=x,
                        y=y,
                        button="left",
                        clickCount=1)
        tab.call_method("Input.dispatchMouseEvent",
                        type="mouseReleased",
                        x=x,
                        y=y,
                        button="left",
                        clickCount=1)
        print(f"Clicked {element_name}.")
    except Exception as e:
        print(f"Error clicking {element_name}:", e)
        return False
    return True


def type_text(tab, text, delay=0.05):
    """
    Insert text using Input.insertText, then dispatch an input event.
    """
    try:
        result = tab.call_method("Input.insertText", text=text)
        print("Result of insertText:", result)
    except Exception as e:
        print("Error during insertText:", e)

    js_input_event = """
    (() => {
        if(document.activeElement){
            document.activeElement.dispatchEvent(new Event('input', { bubbles: true }));
            return true;
        }
        return false;
    })();
    """
    input_event_result = tab.call_method("Runtime.evaluate", expression=js_input_event)
    print("Result of dispatching input event:", input_event_result)


# --- Main Script ---

# Connect to Chrome (ensure Chrome is running with --remote-debugging-port=9222)
browser = pychrome.Browser(url="http://127.0.0.1:9222")
target_tab = attach_to_tab(browser, "Home / X")

print("Navigating to Twitter's tweet composition page...")
target_tab.call_method("Page.navigate", url="https://twitter.com/compose/tweet")
time.sleep(5)  # Wait for the page to load

target_tab.call_method("Runtime.enable")

# Click the tweet box using fixed coordinates: (805, 173)
tweet_box_coords = {"x": 805, "y": 173}
if not click_element_at(target_tab, tweet_box_coords, element_name="tweet box"):
    print("Tweet box could not be clicked; aborting.")
    target_tab.stop()
    exit()

time.sleep(1)  # Allow time for focus

tweet_text = "Your tweet text goes here!"

print("Inserting tweet text...")
type_text(target_tab, tweet_text)
time.sleep(2)

# Click the tweet button (POST) using fixed coordinates: (1533, 296)
post_button_coords = {"x": 1533, "y": 296}
if not click_element_at(target_tab, post_button_coords, element_name="tweet button"):
    print("Tweet button could not be clicked.")
else:
    print("Tweet button click attempted.")

time.sleep(2)

# Click the "Save post" confirmation button using fixed coordinates: (1230, 520)
save_button_coords = {"x": 1230, "y": 520}
if not click_element_at(target_tab, save_button_coords, element_name="save post button"):
    print("Save post button could not be clicked.")
else:
    print("Save post button click attempted.")

time.sleep(3)
target_tab.stop()
print("Script finished.")
