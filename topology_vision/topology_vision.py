import os
import base64
import logging
from PIL import Image
from io import BytesIO
import streamlit as st
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
import google.generativeai as genai

# Load API keys
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Logging configuration
logging.basicConfig(level=logging.INFO)

st.set_page_config(
    page_title="Selector Visual Config Generator",  # Custom title for the tab
    page_icon="🔍"  # Magnifying glass emoji
)

# Convert image to base64 string (OpenAI expects this format)
def image_to_base64(image: Image.Image) -> str:
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# OpenAI analyzes the image (multimodal)
def openai_analysis(base64_image, prompt):
    messages = [
        {
            "role": "user",
            "content": [
f"""
You are a senior network automation engineer.

Analyze the uploaded network topology diagram alongside this textual goal: "{prompt}"

** Important Guardrails: **
If the uploaded image is not a network topology diagram, do not generate any configuration. Instead, return an error message indicating that the image is not suitable for configuration generation. For example if they upload the image of a hotdog.

Generate **device-level configuration blocks** for all visible routers and switches. Assume routers operate at Layer3 and switches at Layer2. Do not enable routing on switches unless explicitly mentioned in the prompt or visible in the diagram.

Unless otherwise specified, assume all routers and switches have management IPs configured and are reachable. Do not assume any specific IP addresses or VLANs unless they are explicitly mentioned in the prompt or visible in the diagram.
---

🔍 Focus Areas (if visible in the diagram or implied by prompt):

- VLANs and inter-VLAN routing
- Subnetting and interface IP addressing
- OSPF, BGP, EIGRP, or IS-IS routing (with correct areas/ASNs)
- Spanning Tree configuration (e.g., root bridge, mode)
- VRFs, ACLs, NAT, trunk/access port settings
- High availability (e.g., HSRP, VRRP)
- Explicit interface names and types
- Logical groupings per device (R1, SW2, etc.)
- Do *not* make assumptions about adding anything not visible in the diagram or specified in the prompt
    -- Do NOT abitrarily add interfaces, VLANs, or protocols or management addresses not shown in the diagram
    -- Do NOT add any placeholder text like "x.x.x.x" or "VLAN 100" unless explicitly mentioned in the prompt
    -- Do NOT add any comments or explanations in the configuration blocks
- Do not add ```text or ```bash tags around the configuration blocks
---

📘 Best Practices and Configuration Guidelines

🔹 **Access Interfaces**
- Use `switchport mode access`
- Assign the correct `switchport access vlan`
- Enable `spanning-tree portfast`
- Enable `spanning-tree bpduguard enable`
- Add `description` for the port (e.g., `description User Port`)
  
🔹 **Trunk Interfaces**
- Use `switchport trunk encapsulation dot1q` (if required)
- Use `switchport mode trunk`
- Explicitly list allowed VLANs: `switchport trunk allowed vlan X,Y,Z`
- Enable `spanning-tree portfast trunk` on edge trunk ports if safe

🔹 **Spanning Tree Configuration**
- Use `spanning-tree mode rapid-pvst` or `mst`
- Set bridge priority: `spanning-tree vlan X priority 4096` for core switches
- Avoid using `spanning-tree portfast` on core uplinks

🔹 **OSPF Configuration**
- Use correct area IDs (e.g., area 0 for backbone)
- Use loopbacks as router IDs where possible
- Use `passive-interface` for access interfaces
- Use `ip ospf cost` to tune metrics on interfaces

🔹 **BGP Configuration**
- Define local ASN: `router bgp <ASN>`
- Use `neighbor <IP> remote-as <ASN>` for external peers
- Use `update-source loopback0` if peering via loopbacks
- Include network statements or redistribute routes properly

🔹 **EIGRP Configuration**
- Use named EIGRP if possible
- Define `network` statements appropriately
- Use `passive-interface` on unused links
- Configure `hello`/`hold` timers for WAN links if needed

🔹 **IS-IS Configuration**
- Enable IS-IS on interfaces: `ip router isis`
- Use net-id: `net 49.0001.0000.0000.0001.00`
- Define levels: `is-type level-2-only`
- Assign unique system IDs per router

🔹 **Static Routes**
- Use `ip route` with next-hop or exit-interface
- Avoid circular routing or black holes

🔹 **ACLs and Security**
- Use named ACLs with `ip access-list extended NAME`
- Place ACLs closest to the source when possible
- Include `deny ip any any log` at the end for audit
- Use `access-class` on VTY lines to restrict access
- Enable `service password-encryption` and `no ip http server`

---

📌 Output Instructions:

- Return only clean, production-ready Cisco-style CLI configuration blocks
- Group by device (clearly separate each config)
- Use consistent indentation and interface naming
- Do **not** include explanations, markdown formatting, or triple backticks
"""
,
                {"image": base64_image, "resize": 768},
            ],
        }
    ]
    result = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        max_tokens=2000,
    )
    return result.choices[0].message.content.strip()

# Gemini analyzes the image
def gemini_analysis(image: Image.Image, prompt):
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-pro")

    response = model.generate_content(
        [
            image,
f"""
You are a senior network automation engineer.

Analyze the uploaded network topology diagram alongside this textual goal: "{prompt}"

Generate **device-level configuration blocks** for all visible routers and switches. Assume routers operate at Layer3 and switches at Layer2. Do not enable routing on switches unless explicitly mentioned in the prompt or visible in the diagram.

Unless otherwise specified, assume all routers and switches have management IPs configured and are reachable. Do not assume any specific IP addresses or VLANs unless they are explicitly mentioned in the prompt or visible in the diagram.
---

🔍 Focus Areas (if visible in the diagram or implied by prompt):

- VLANs and inter-VLAN routing
- Subnetting and interface IP addressing
- OSPF, BGP, EIGRP, or IS-IS routing (with correct areas/ASNs)
- Spanning Tree configuration (e.g., root bridge, mode)
- VRFs, ACLs, NAT, trunk/access port settings
- High availability (e.g., HSRP, VRRP)
- Explicit interface names and types
- Logical groupings per device (R1, SW2, etc.)

---

📘 Best Practices and Configuration Guidelines

🔹 **Access Interfaces**
- Use `switchport mode access`
- Assign the correct `switchport access vlan`
- Enable `spanning-tree portfast`
- Enable `spanning-tree bpduguard enable`
- Add `description` for the port (e.g., `description User Port`)
  
🔹 **Trunk Interfaces**
- Use `switchport trunk encapsulation dot1q` (if required)
- Use `switchport mode trunk`
- Explicitly list allowed VLANs: `switchport trunk allowed vlan X,Y,Z`
- Enable `spanning-tree portfast trunk` on edge trunk ports if safe

🔹 **Spanning Tree Configuration**
- Use `spanning-tree mode rapid-pvst` or `mst`
- Set bridge priority: `spanning-tree vlan X priority 4096` for core switches
- Avoid using `spanning-tree portfast` on core uplinks

🔹 **OSPF Configuration**
- Use correct area IDs (e.g., area 0 for backbone)
- Use loopbacks as router IDs where possible
- Use `passive-interface` for access interfaces
- Use `ip ospf cost` to tune metrics on interfaces

🔹 **BGP Configuration**
- Define local ASN: `router bgp <ASN>`
- Use `neighbor <IP> remote-as <ASN>` for external peers
- Use `update-source loopback0` if peering via loopbacks
- Include network statements or redistribute routes properly

🔹 **EIGRP Configuration**
- Use named EIGRP if possible
- Define `network` statements appropriately
- Use `passive-interface` on unused links
- Configure `hello`/`hold` timers for WAN links if needed

🔹 **IS-IS Configuration**
- Enable IS-IS on interfaces: `ip router isis`
- Use net-id: `net 49.0001.0000.0000.0001.00`
- Define levels: `is-type level-2-only`
- Assign unique system IDs per router

🔹 **Static Routes**
- Use `ip route` with next-hop or exit-interface
- Avoid circular routing or black holes

🔹 **ACLs and Security**
- Use named ACLs with `ip access-list extended NAME`
- Place ACLs closest to the source when possible
- Include `deny ip any any log` at the end for audit
- Use `access-class` on VTY lines to restrict access
- Enable `service password-encryption` and `no ip http server`

---

📌 Output Instructions:

- Return only clean, production-ready Cisco-style CLI configuration blocks
- Group by device (clearly separate each config)
- Use consistent indentation and interface naming
- Do **not** include explanations, markdown formatting, or triple backticks
"""
        ],
        generation_config={"temperature": 0.4}
    )

    return response.text.strip()

# Gemini reviews and improves OpenAI's config
def gemini_review(openai_output: str):
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-pro")

    response = model.generate_content([
        f"""
You are a senior network engineer reviewing a Cisco-style configuration generated by another AI model (OpenAI).

Unless otherwise specified, assume all routers and switches have management IPs configured and are reachable. Do not assume any specific IP addresses or VLANs unless they are explicitly mentioned in the prompt or visible in the diagram.

Please perform a line-by-line audit of the configuration for:
- Technical accuracy and syntax correctness
- Interface consistency and VLAN accuracy
- OSPF/BGP/EIGRP/IS-IS protocol correctness
- STP, trunking, access port logic, and ACL alignment
- Best practices, formatting, indentation, and readability

📌 Output Instructions:
- Return a revised version of the configuration only
- Group configuration blocks clearly by device (e.g., R1, SW2)
- Do not include explanations, commentary, markdown, or triple backticks
- Use production-ready syntax — no placeholders unless unavoidable

Here is the original configuration to review and improve:
{openai_output}
"""
    ])
    return response.text.strip()

# OpenAI reviews and improves Gemini's config
def openai_review(gemini_output: str):
    messages = [
        {
            "role": "system",
            "content": "You are a senior Cisco network engineer reviewing a configuration generated by another AI (Google Gemini)."
        },
        {
            "role": "user",
            "content": f"""
You are a senior network engineer reviewing a Cisco-style configuration generated by another AI model (OpenAI).

Unless otherwise specified, assume all routers and switches have management IPs configured and are reachable. Do not assume any specific IP addresses or VLANs unless they are explicitly mentioned in the prompt or visible in the diagram.

Please perform a line-by-line audit of the configuration for:
- Technical accuracy and syntax correctness
- Interface consistency and VLAN accuracy
- OSPF/BGP/EIGRP/IS-IS protocol correctness
- STP, trunking, access port logic, and ACL alignment
- Best practices, formatting, indentation, and readability

📌 Output Instructions:
- Return a revised version of the configuration only
- Group configuration blocks clearly by device (e.g., R1, SW2)
- Do not include explanations, commentary, markdown, or triple backticks
- Use production-ready syntax — no placeholders unless unavoidable

Here is the original configuration to review and improve:
{gemini_output}
"""
        }
    ]
    result = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=3000,
    )
    return result.choices[0].message.content.strip()

# Final synthesis by OpenAI
def gemini_synthesis(revised_openai, revised_gemini, image: Image.Image, original_prompt: str):
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-pro")

    response = model.generate_content(
        [
            image,
            f"""
You are a senior network automation engineer.

Unless otherwise specified, assume all routers and switches have management IPs configured and are reachable. Do not assume any specific IP addresses or VLANs unless they are explicitly mentioned in the prompt or visible in the diagram.

You are given two independently reviewed Cisco-style configurations for a network topology diagram and a configuration prompt. Your task is to synthesize the best ideas from both into a single, final configuration.

---

📄 Original Prompt:
\"\"\"
{original_prompt}
\"\"\"

🔵 Revised OpenAI configuration:
{revised_openai}

🟢 Revised Gemini configuration:
{revised_gemini}

---

🎯 Synthesis Objectives:

1. **Merge** the most accurate and optimized parts from both inputs
2. **Resolve conflicts** where OpenAI and Gemini disagree — prefer correctness, clarity, and Cisco best practices
3. **Eliminate duplication** (e.g., repeated interface blocks or identical routing statements)
4. **Group configuration blocks by device** (e.g., R1, SW1, etc.) with clear separation
5. **Validate logic** across routing, VLANs, ACLs, STP, redundancy, and interface assignments

---

📌 Output Requirements:

- Return only clean, production-ready CLI configuration blocks
- Use Cisco-style syntax with consistent indentation
- Group by device with headers (e.g., `! Device: R1`)
- Do **not** include explanations, commentary, or markdown formatting
- Do **not** use triple backticks, code blocks, or tags like "plaintext"
- Avoid any placeholder text unless absolutely necessary (e.g., `x.x.x.x`)

---
Now generate the final configuration.
"""
        ],
        generation_config={"temperature": 0.7}
    )

    return response.text.strip()

# UI
st.image('logo.jpeg')
st.title("🧠 Visual Configuration Generator")
st.markdown("""
Welcome to the **Selector Visual Configuration Generator** — a multimodal AI-powered tool designed to analyze your **network diagrams** and generate optimized, CLI-style configurations.

---

### ⚙️ How It Works

1. **Upload a network diagram** (PNG, JPG, or JPEG).
2. **Describe your configuration goal** — this **text prompt is just as important as the image**.  
   The more context you provide (e.g., device roles, protocols, design intentions), the better the output.
3. Our AI pipeline will:
   - 🧠 Use **OpenAI** to generate an initial configuration from the image and prompt
   - 🤖 Use **Google Gemini** to generate a second, independent interpretation
   - 🔄 Cross-review both configurations for correctness and consistency
   - 🧬 Merge them into a **final, clean, and optimized configuration**
4. ✅ View, explain, and **download** your final device configurations.

---

### ✍️ Prompt Tips for Best Results

- Be specific: _“Inter-VLAN routing with ACLs blocking Guest-to-Admin traffic”_
- Mention desired protocols: _“Use OSPF area 0 between routers”_
- Clarify design intent: _“Router 1 is WAN edge, Router 2 is core”_
- Include the operating systems if they are no present in the diagram: _“Cisco IOS, Juniper Junos”_
- Describe any **security requirements**: _“ACLs to restrict access between VLANs”_
- Specify **redundancy**: _“Use HSRP for gateway redundancy”_
- Mention any **specific features**: _“Enable DHCP snooping on VLAN 10”_
- If you have a **table of IP addresses** or VLANs, include it in the prompt.

The more **textual detail** you give, the more accurate and useful your configuration will be.

---
""")

st.markdown("## 🧪 Sample Topology Diagrams")
st.markdown("### 🧰 Try These Network Topology Examples")

# Load and show the samples
col1, col2 = st.columns(2)

with col1:
    st.image("ros.png", caption="Router on a Stick", use_container_width =True)
    with open("ros.png", "rb") as f:
        st.download_button("📥 Download ROS Sample", f, file_name="ros.png")

with col2:
    st.image("napkin.png", caption="Napkin Diagram", use_container_width =True)
    with open("napkin.png", "rb") as f:
        st.download_button("📥 Download Napkin Sample", f, file_name="napkin.png")

st.markdown("### 📤 Upload Your Own Network Diagram")

uploaded_file = st.file_uploader("Upload network diagram (PNG, JPG, JPEG)", type=["png", "jpg", "jpeg"])

prompt = st.text_area("Configuration Goal", placeholder="Example: Configure inter-VLAN routing and ACLs for a dual-router setup")

if st.button("Submit"):
    if uploaded_file and prompt:
        image = Image.open(uploaded_file)
        base64_img = image_to_base64(image)

        st.info("⚙️ Processing your diagram and generating configurations...")

        # Step 1 - Raw OpenAI output
        with st.spinner("🧠 OpenAI analyzing image and generating initial proposal..."):
            openai_raw = openai_analysis(base64_img, prompt)

        # Step 2 - Raw Gemini output
        with st.spinner("🤖 Gemini analyzing image and generating initial proposal..."):
            gemini_raw = gemini_analysis(image, prompt)

        # Step 3 - Gemini reviews OpenAI
        with st.spinner("🔍 Gemini reviewing OpenAI's configuration..."):
            revised_openai = gemini_review(openai_raw)

        # Step 4 - OpenAI reviews Gemini
        with st.spinner("🔍 OpenAI reviewing Gemini's configuration..."):
            revised_gemini = openai_review(gemini_raw)

        # Step 5 - Final synthesis
        with st.spinner("🧬 Synthesizing final configuration..."):
            final_config = gemini_synthesis(revised_openai, revised_gemini, image, prompt)
            st.session_state["final_config"] = final_config

        st.success("✅ Configuration generation complete!")

        # 🧩 Final result outside expander
        st.subheader("🧩 Final Merged Configuration")
        st.image(image, caption="Uploaded Network Diagram")
        st.code(final_config, language="bash")

        # 🔬 Intermediate results inside expander
        with st.expander("🔬 View Intermediate AI Steps", expanded=False):
            st.markdown("##### 📦 OpenAI Raw Configuration")
            st.code(openai_raw, language="bash")

            st.markdown("##### 🤖 Gemini Raw Configuration")
            st.code(gemini_raw, language="bash")

            st.markdown("##### 🔍 Gemini-Revised OpenAI Configuration")
            st.code(revised_openai, language="bash")

            st.markdown("##### 🔍 OpenAI-Revised Gemini Configuration")
            st.code(revised_gemini, language="bash")
    else:
        st.warning("⚠️ Please upload a diagram and provide a configuration goal.")

# 🔁 Post-submit UI: only shows if config was generated
if "final_config" in st.session_state:   
    if "uploaded_image_bytes" in st.session_state:
        st.image(st.session_state["uploaded_image_bytes"], caption="Uploaded Network Diagram", use_container_width=True)
    # Explanation button
    if st.button("🧠 Explain This Configuration"):
        with st.spinner("Explaining the final configuration..."):
            explanation = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You're a Cisco network instructor."},
                    {"role": "user", "content": f"Explain the following configuration:\n{st.session_state['final_config']}"}
                ]
            ).choices[0].message.content.strip()
        st.markdown(explanation)

    # Download button
    st.download_button(
        label="📥 Download Final Configuration",
        data=st.session_state["final_config"],
        file_name="Selector_Configuration_Vision_Recommended_Config.md",
        mime="text/plain",
    )