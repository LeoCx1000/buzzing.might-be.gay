const proto = location.protocol === "https:" ? "wss" : "ws";
const host_ws = new WebSocket(`${proto}://${location.host}/host/ws`);

const message_box = document.getElementById("message");

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
document.getElementById("toggle-lock").onclick = () => { send("TOGGLE_LOCK") }


const send = (event, data = {}) => (host_ws.send(JSON.stringify({ "event": event, ...data })))

host_ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)

    switch (msg.event) {
        case "UPDATE":
            updateBuzzers(msg.users);
            if (msg.sound) buzz()
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
                    <span class="displayname">${user.name}</span>
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