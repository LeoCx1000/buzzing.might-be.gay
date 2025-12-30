const proto = location.protocol === "https:" ? "wss" : "ws";
const buzzer_ws = new WebSocket(`${proto}://${location.host}/buzzer/ws`);

const btn = document.getElementById("buzz");
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

var state = "OPEN";

buzzer_ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)

    switch (msg.event) {
        case "UPDATE":
            updateBuzzers(msg.users);
            updatebtn(msg.button_state);
            if (msg.sound)
                buzz()
            break;
        case "RESET":
            updateBuzzers([]);
            updatebtn("OPEN")
            break;
        case "PING":
            send("PONG", { "id": msg.id })
            break;
    }
}

const updatebtn = (newState) => {
    if (newState)
        state = newState;

    switch (state) {
        case "OPEN":
            btn.style.borderColor = "green";
            btn.style.backgroundColor = "lightgreen";
            btn.innerHTML = "BUZZ";

            break;
        case "BUZZED":
            btn.style.borderColor = "red";
            btn.style.backgroundColor = "lightcoral";
            btn.innerHTML = "BUZZED";
            break;
        case "LOCKED":
            btn.style.borderColor = "yellow";
            btn.style.backgroundColor = "lightyellow";
            btn.innerHTML = "LOCKED";
            break;
        case "DISCONNECT":
            btn.style.borderColor = "yellow";
            btn.style.backgroundColor = "lightyellow";
            btn.innerHTML = "LOST CONN";
            break;
    }
}

btn.onclick = () => {
    if (state == "OPEN") {
        send("BUZZ")
        updatebtn("BUZZED")
    }
}

document.body.addEventListener("keydown", function (e) {
    if (e.key == ' ') {
        btn.onclick()
    }
});


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
                    <span class="displayname">${user.name}</span>
                </div>`
            list.appendChild(li);
        }
    }
    else {
        list.innerHTML = "<p>No users have buzzed...</p>"
    }
}

const leaveBtn = document.getElementById("leave")
leaveBtn.onclick = () => {
    if (confirm("Leave game?")) {
        send("LEAVE")
    }
}