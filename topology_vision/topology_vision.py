import os
import logging
from PIL import Image
from io import BytesIO
import streamlit as st
from dotenv import load_dotenv
import google.generativeai as genai

# --- Initialization ---
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
logging.basicConfig(level=logging.INFO)

st.set_page_config(page_title="Visual Config Generator", page_icon="🔍")
st.image("logo.jpeg")
st.title("🧠 Visual Configuration Generator")

# --- Model Setup ---
MODEL = None
if GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        MODEL = genai.GenerativeModel("gemini-2.5-pro")
    except Exception as e:
        st.error(f"Failed to initialize Gemini model: {e}")
else:
    st.error("🚨 GOOGLE_API_KEY not found. Please set it in your .env file.")

# --- Prompt Instructions ---
st.markdown("""
Welcome to the **Visual Configuration Generator**

---
### ⚙️ How It Works
1. **Upload a network diagram** (PNG, JPG, or JPEG).
2. **Describe your configuration goal**.
3. Google's **Gemini 2.5 Pro** will analyze both and generate optimized CLI configurations.
4. ✅ View and download your final device configurations.

---
### ✍️ Prompt Tips
- Be specific: _"Inter-VLAN routing with ACLs blocking Guest-to-Admin traffic"_
- Mention protocols: _"Use OSPF area 0 between routers"_
- Design intent: _"Router 1 is WAN edge, Router 2 is core"_
- Operating systems: _"Cisco IOS, Juniper Junos"_
- Security: _"ACLs to restrict access between VLANs"_
- Redundancy: _"Use HSRP for gateway redundancy"_
- Features: _"Enable DHCP snooping on VLAN 10"_
- Include tables if applicable
---
""")

# --- Upload UI ---
uploaded_file = st.file_uploader("Upload network diagram", type=["png", "jpg", "jpeg"])
prompt = st.text_area("Configuration Goal", placeholder="Example: Configure inter-VLAN routing and OSPF Area 0.")

# --- Generator Class ---
class VisualConfigGenerator:
    def __init__(self, model, prompt, image):
        self.model = model
        self.prompt = prompt
        self.image = image

    def build_prompt(self):
        return f"""
    You are an expert network automation engineer. Your task is to generate a production-ready, Cisco-style CLI configuration based on an uploaded network diagram and a textual goal.

    **Primary Goal:**
    Analyze the network topology diagram and the following user request to generate complete and accurate device configurations.
    - **User Request:** "{prompt}"

    ---
    **Configuration Guidelines & Best Practices:**

    **General:**
    - Assume routers operate at Layer 3 and switches at Layer 2.
    - Do not enable routing on switches unless explicitly required.
    - Do not invent IP addresses or VLANs unless they are present in the diagram or prompt.

    **Interfaces:**
    - **Access Ports:** Use `switchport mode access`, assign a `switchport access vlan`, and enable `spanning-tree portfast` and `bpduguard`.
    - **Trunk Ports:** Use `switchport mode trunk`, `switchport trunk encapsulation dot1q`, and specify `switchport trunk allowed vlan`.
    - **Always assume intefaces should be enabled if you add configuration to them unless specified otherwise.

    **Routing Protocols:**
    *** OSPF (Open Shortest Path First) ***:
     - Configure the process using router ospf <process-id>.
     - Define a unique router-id for each device, preferably from a stable loopback interface.
     - Advertise networks using network <IP-address> <wildcard-mask> area <area-id>.
     - Use area 0 for the backbone. Other non-backbone areas must connect to area 0.
     - Prevent routing updates on LAN-facing interfaces with passive-interface <interface-name>.
     - Manually tune paths by setting ip ospf cost <value> on interfaces.
    
    *** BGP (Border Gateway Protocol) ***:
     - Define the local router's ASN with router bgp <local-ASN>.
     - Establish neighborships using neighbor <IP-address> remote-as <remote-ASN>.
     - For iBGP, ensure neighbors have update-source loopback0 and next-hop-self configured where appropriate.
     - For eBGP, neighbors are typically on directly connected links.
     - Activate address families like address-family ipv4 unicast to exchange prefixes.
     - Advertise local networks with the network <prefix> mask <mask> command.
     - Implement policy control using route-map applied to neighbors.

    *** EIGRP (Enhanced Interior Gateway Routing Protocol) ***:
     - Enable the process with router eigrp <ASN>. Named mode (router eigrp <NAME>) is preferred.
     - Under the address family, define the ASN: address-family ipv4 unicast autonomous-system <ASN>.
     - Advertise networks with precise network <IP-address> <wildcard-mask> statements.
     - Use passive-interface on links where you don't want EIGRP neighbors to form.
     - Configure summarization on key interfaces (ip summary-address eigrp <ASN> ...) to optimize routing tables.
     - Use eigrp stub on spoke routers in hub-and-spoke topologies.
     
    *** IS-IS (Intermediate System to Intermediate System) ***:
     - Enable the routing process globally with router isis.
     - Define the router's unique Network Entity Title (NET) address, e.g., net 49.0001.aaaa.bbbb.cccc.00. The area ID is the 49.0001 portion, and the system ID is aaaa.bbbb.cccc. The 00 is the NSEL.
     - Specify the router's role with is-type level-1, level-2-only, or level-1-2.
     - Enable IS-IS on a per-interface basis using ip router isis.

    *** Static Routing ***:
     - Use for simple, predictable paths or as a backup.
     - Define a route with ip route <destination-prefix> <subnet-mask> <next-hop-IP | exit-interface>.
     - Create a floating static route for backup by adding a higher administrative distance (e.g., ip route ... 250). This route only becomes active if the primary, lower-distance route fails.
     - Define a default route to catch all traffic not otherwise specified in the routing table using ip route 0.0.0.0 0.0.0.0 <next-hop-IP | exit-interface>.

    **Security:**
    - Apply basic hardening: `service password-encryption`, `no ip http server`.
    - Use named ACLs (`ip access-list extended NAME`) when security rules are requested.

    ---
    **Output Instructions (Crucial):**

    - **CRITICAL:** Return **only** the clean, ready-to-use CLI configuration blocks.
    - Group the configuration logically for each device using a comment header (e.g., `! Device: R1`).
    - Use consistent indentation.
    - Do **not** include any explanations, commentary, markdown formatting (like ```), or conversational text in your output.
    """

    def run(self):
        try:
            logging.info("Sending request to Gemini model...")
            response = self.model.generate_content(
                [self.image, self.build_prompt()],
                generation_config={"temperature": 0.4},
                request_options={"timeout": 180}
            )
            logging.info("Gemini model response received")
            return response.text.strip() if hasattr(response, "text") else None
        except Exception as e:
            logging.error(f"Gemini failed: {e}")
            return None

# --- Trigger Logic ---
if st.button("🚀 Submit to Topology Vision"):
    if uploaded_file and prompt and MODEL:
        st.session_state["trigger_config"] = True
        st.session_state["prompt_text"] = prompt
        st.session_state["uploaded_image"] = uploaded_file.getvalue()
        st.session_state["final_config_ready"] = False  # clear old results
        st.rerun()
    else:
        st.warning("Please provide all required inputs.")

# --- Process and Display Output ---
if st.session_state.get("trigger_config"):
    image = Image.open(BytesIO(st.session_state["uploaded_image"]))
    generator = VisualConfigGenerator(MODEL, st.session_state["prompt_text"], image)

    with st.spinner("🤖 Gemini is analyzing..."):
        result = generator.run()

    if result:
        st.session_state["final_config"] = result
        st.session_state["final_config_ready"] = True
    else:
        st.error("Gemini failed to generate configuration.")
        st.session_state["final_config_ready"] = False

    st.session_state["trigger_config"] = False

# --- Render Config Output ---
if st.session_state.get("final_config_ready"):
    st.subheader("🧩 Final Configuration")
    st.code(st.session_state["final_config"], language="bash")

    if st.button("🤠 Explain This Configuration"):
        with st.spinner("Explaining configuration..."):
            try:
                explain_prompt = f"""
                You are a helpful Cisco instructor. Explain the following CLI config section-by-section:
                {st.session_state['final_config']}
                """
                response = MODEL.generate_content(explain_prompt)
                st.session_state["final_explanation"] = response.text.strip()
            except Exception as e:
                st.error(f"Explanation error: {e}")

    if st.session_state.get("final_explanation"):
        st.markdown(st.session_state["final_explanation"])

    st.download_button("📥 Download Final Configuration",
                       data=st.session_state["final_config"],
                       file_name="generated_network_config.txt",
                       mime="text/plain")
