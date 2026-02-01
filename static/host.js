const proto = location.protocol === "https:" ? "wss" : "ws";
const host_ws = new WebSocket(`${proto}://${location.host}/host/ws`);

const message_box = document.getElementById("message");
var locked = false;

host_ws.onclose = (e) => {
    if (e.code == 1000) {
        window.location.replace('/host?error=4')
        // closed by the host
    }
    else {
        message_box.innerHTML = `<p>${e.reason || "Lost Connection"}(${e.code})</p><br><a href='/buzzer'>Retry.</a>`;
        message_box.style.display = "inline-block";
    }


}

document.getElementById("reset").onclick = () => { send("RESET") }
document.getElementById("toggle-lock").onclick = () => {
    locked = !locked;
    updatebtn(locked)
    send("TOGGLE_LOCK")
}


const send = (event, data = {}) => (host_ws.send(JSON.stringify({ "event": event, ...data })))

host_ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)

    switch (msg.event) {
        case "UPDATE":
            updateBuzzers(msg.users);
            updatebtn(msg.button_state == "LOCKED")
            if (msg.sound) buzz()
            break;
    }
}

function updatebtn(state) {
    locked = state;
    const button = document.querySelector(".admin-buttons")
    if (state) {
        button.style.backgroundColor = "yellow";
        document.getElementById("toggle-lock").innerText = "Unlock Buzzer"
    }
    else {
        button.style.backgroundColor = "green";
        document.getElementById("toggle-lock").innerText = "Lock Buzzer"
    }
}



function updateBuzzers(users) {
    const list = document.getElementById("buzzed-users")
    list.innerHTML = "";

    if (users.length != 0) {
        for (const user of users) {
            const li = document.createElement("li");
            li.classList.add(user.buzzed ? "buzzed" : "unbuzzed")
            li.innerHTML = `
                <div class="username${user.connected ? '' : ' connLost'}">
                    <img class="avatar" src="${user.avatar}?size=32"/>
                    <span class="displayname">${user.name} ${user.choice ? " (" + user.choice + ")" : ""}</span>
                </div>`
            list.appendChild(li);
        }
    }
    else {
        list.innerHTML = "<p>No users have buzzed...</p>"
    }
}

const audioToggle = document.getElementById("audio")

function buzz() {
    if (audioToggle.checked) {
        const audio = new Audio("/static/buzz.wav")
        audio.volume = 0.2;
        audio.play();
    }
}

function auto_grow(element) {
    element.style.height = "5px";
    element.style.height = (element.scrollHeight) + "px";
}

document.getElementById("promptForm").onsubmit = (e) => {
    console.log("This function")
    console.log(e)
    console.log(e.target[0].value)
    e.preventDefault()
    send("PROMPT_CHOICES", { "choices": e.target[0].value })
}

document.getElementById("clearChoices").onclick = (e) => {
    e.preventDefault()
    send("CLEAR_MC")
}

document.getElementById("earlyEndMC").onclick = (e) => {
    e.preventDefault()
    send("END_MC")
}

document.getElementById("prompts").oninput = (e) => { auto_grow(e.target) }