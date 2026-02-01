const proto = location.protocol === "https:" ? "wss" : "ws";
const buzzer_ws = new WebSocket(`${proto}://${location.host}/buzzer/ws`);

const buzzer_button = document.getElementById("buzz");
const message_box = document.getElementById("message");

buzzer_ws.onclose = (e) => {
    if (e.code == 1000) {
        window.location.replace('/buzzer?error=4')
        // closed by the host
    }
    else if (e.code == 1013) {
        message_box.innerHTML = `<p>You left.</p><a href='${location.href}'>Rejoin.</a> <a href="/">Go home.</a>`;
        message_box.style.display = "inline-block";
        updatebtn("DISCONNECT");

    }
    else {
        message_box.innerHTML = `<p>${e.reason || "Lost Connection"}(${e.code})</p><br><a href='/buzzer'>Retry.</a>`;
        message_box.style.display = "inline-block";
        updatebtn("DISCONNECT");
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

const send = (event, data = {}) => (buzzer_ws.send(JSON.stringify({ "event": event, ...data })))

var buzzer_state = "OPEN";

buzzer_ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)

    console.log("WS Receive", msg)
    switch (msg.event) {
        case "UPDATE":
            updateBuzzers(msg.users);
            updatebtn(msg.button_state);
            if (msg.sound)
                buzz()
            if (msg.choice) {
                console.log(msg.choice)
                console.log(typeof msg.choice)
                document.getElementById("selfChoice").innerText = `Your Choice: ${msg.choice}`
            } else {
                document.getElementById("selfChoice").innerText = ""
            }
            if (!msg.choices) {
                document.getElementById("selfChoice").innerText = "";
                break;
            }
            if (msg.choice)
                break
        case "MULTIPLE_CHOICE":
            promptMultipleChoice(msg.choices)
            break;
        case "RESET":
            updateBuzzers([]);
            updatebtn("OPEN")
            break;
        case "PING":
            send("PONG", { "id": msg.id })
            break;
        case "END_MULTIPLE_CHOICE":
            endMultipleChoice();
            break;
    }
}

function promptMultipleChoice(choices) {
    updatebtn("LOCKED")
    const form = document.getElementById("multipleChoiceForm")
    form.innerHTML = ""
    for (const elem of choices) {
        const btn = document.createElement("button")
        btn.classList.add("multipleChoiceBtn")
        btn.innerText = elem
        form.appendChild(btn)
    }
    document.getElementById("multipleChoicePopup").classList.remove("hidden")
    const body = document.getElementById("body")
    if (!body.classList.contains("noscroll"))
        body.classList.add("noscroll")
}

function endMultipleChoice() {
    const popup = document.getElementById("multipleChoicePopup")
    if (!popup.classList.contains("hidden"))
        popup.classList.add("hidden")
    document.getElementById("body").classList.remove("noscroll")

}

function updatebtn(newState) {
    if (newState)
        buzzer_state = newState;

    switch (buzzer_state) {
        case "OPEN":
            buzzer_button.style.borderColor = "green";
            buzzer_button.style.backgroundColor = "lightgreen";
            buzzer_button.innerHTML = "BUZZ";

            break;
        case "BUZZED":
            buzzer_button.style.borderColor = "red";
            buzzer_button.style.backgroundColor = "lightcoral";
            buzzer_button.innerHTML = "BUZZED";
            break;
        case "LOCKED":
            buzzer_button.style.borderColor = "yellow";
            buzzer_button.style.backgroundColor = "lightyellow";
            buzzer_button.innerHTML = "LOCKED";
            break;
        case "DISCONNECT":
            buzzer_button.style.borderColor = "yellow";
            buzzer_button.style.backgroundColor = "lightyellow";
            buzzer_button.innerHTML = "LOST CONN";
            break;
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
                <div class="username">
                    <img class="avatar" src="${user.avatar}?size=32"/>
                    <span class="displayname">${user.name}${user.choice ? " (" + user.choice + ")" : ""}</span>
                </div>`
            list.appendChild(li);
        }
    }
    else {
        list.innerHTML = "<p>No users have buzzed...</p>"
    }
}

document.getElementById("leave").onclick = () => {
    if (confirm("Leave game?")) {
        send("LEAVE")
    }
}

document.body.addEventListener("keydown", function (e) {
    if (e.key == ' ') {
        buzzer_button.onclick()
    }
});

document.getElementById("multipleChoiceForm").onsubmit = (e) => {
    e.preventDefault();
    console.log(e)
}

document.addEventListener('click', async (e) => {
    if (e.target.matches('button') && e.target.classList.contains('multipleChoiceBtn')) {
        console.log("clock")
        document.getElementById("selfChoice").innerText = `Your Choice: ${e.target.innerText}`
        send("MC_ANSWER", { "answer": e.target.innerText })
        endMultipleChoice()
    }
});

buzzer_button.onclick = () => {
    if (buzzer_state == "OPEN") {
        send("BUZZ")
        updatebtn("BUZZED")
    }
}