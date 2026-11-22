var streamonitorSettings = {};
init();

function addGlobalEventListener(
	eventType,
	selector,
	callback,
	options,
	parent = document
) {
	parent.addEventListener(
		eventType,
		(e) => {
			if (e.target.matches(selector)) callback(e);
		},
		options
	);
}

function qs(selector, parent = document) {
	return parent.querySelector(selector);
}

function qsa(selector, parent = document) {
	return [...parent.querySelectorAll(selector)];
}

function sendCommand(command) {
	fetch("./api/command?command=" + command)
		.then((data) => {
			return data.text();
		})
		.then((data) => {
			showSnackbarMessage(data);
			loadStreamers();
		});
}

async function init() {
	const response = await fetch("./api/basesettings");
	const json = await response.json();
	streamonitorSettings.sites = json.sites;
	streamonitorSettings.status = json.status;
	streamonitorSettings.groupDownloadInfo = json.groupDownloadInfo;
	fillSiteLists(json.sites);
	fillStatusFilter(json.status);
	addGlobalEventListener("click", "#reload", () => {
		const reloadIcon = qs("#reload i");
		reloadIcon.classList.add("fa-spin");
		loadStreamers();
		setTimeout(() => {
			reloadIcon.classList.remove("fa-spin");
		}, 1000);
	});

	addGlobalEventListener("click", ".streamer_delete", (e) => {
		const streamer = e.target.closest(".streamer-card");
		let deleteConfirm = confirm(
			"Do you really want to delete " +
				streamer.getAttribute("username") +
				"(" +
				streamer.getAttribute("site") +
				")?"
		);
		if (deleteConfirm) {
			let command =
				"remove " +
				streamer.getAttribute("username") +
				" " +
				streamer.getAttribute("site");
			sendCommand(command);
		}
	});

	addGlobalEventListener("click", ".streamer_start", (e) => {
		const streamer = e.target.closest(".streamer-card");
		let command =
			"start " +
			streamer.getAttribute("username") +
			" " +
			streamer.getAttribute("site");
		sendCommand(command);
	});

	addGlobalEventListener("click", ".streamer_stop", (e) => {
		const streamer = e.target.closest(".streamer-card");
		let command =
			"stop " +
			streamer.getAttribute("username") +
			" " +
			streamer.getAttribute("site");
		sendCommand(command);
	});

	addGlobalEventListener("click", ".streamer_edit", (e) => {
		const streamer = e.target.closest(".streamer-card");

		qs("#streamerModal_username").disabled = true;
		qs("#streamerModal_username").value = streamer.getAttribute("username");
		qs("#streamerModal_site").disabled = true;
		qs("#streamerModal_site").value = streamer.getAttribute("site");
		const modal = new bootstrap.Modal(qs("#streamerModal"));
		modal.show();
	});

	loadStreamers();
	setInterval(function () {
		loadStreamers();
	}, 3000);
}

function filterStreamers() {
	const streamer = qsa(".streamer-card");
	const streamerFilter = qs("#streamerFilter").value;
	const siteFilter = qs("#siteFilter").value;
	const statusFilter = qs("#statusFilter").value;
	let count = 0;
	let countVisible = 0;

	streamer.forEach((streamerElem) => {
		let showElem = true;
		if (streamerFilter != "") {
			showElem =
				showElem &&
				wildcardMatch(
					"*" + streamerFilter + "*",
					qs(".streamer_name", streamerElem).innerText
				);
		}
		if (siteFilter != "") {
			showElem =
				showElem && streamerElem.classList.contains("site_" + siteFilter);
		}
		if (statusFilter == "inactive") {
			showElem = showElem && streamerElem.classList.contains("inactive");
		}
		if (statusFilter == "downloading") {
			showElem = showElem && streamerElem.classList.contains("downloading");
		}
		if (statusFilter == "notDownloading") {
			showElem = showElem && streamerElem.classList.contains("notDownloading");
		}
		if (statusFilter == "onlineButNotDownlading") {
			showElem =
				showElem && streamerElem.classList.contains("onlineButNotDownlading");
		}
		if (statusFilter == "private") {
			showElem = showElem && streamerElem.classList.contains("private");
		}
		if (statusFilter == "recording") {
			showElem = showElem && streamerElem.classList.contains("recording");
		}
		count++;
		if (showElem) {
			streamerElem.style.display = "block";
			countVisible++;
		} else {
			streamerElem.style.display = "none";
		}
		let counterText = "";
		if (count == countVisible) {
			counterText = count;
		} else {
			counterText = `${countVisible} of ${count}`;
		}
		qs("#countStreamer").innerText = counterText;
	});
}

function loadStreamers() {
	fetch("./api/data")
		.then((data) => {
			showSnackbarMessage("Streamer reloaded", true);
			return data.json();
		})
		.then((jsonData) => {
			updateOrCreateStreamers(jsonData.streamers);
			updateFreespace(jsonData.freeSpace);
			filterStreamers();
		});
}

function wildcardMatch(wildcard, str) {
	let w = wildcard.replace(/[.+^${}()|[\]\\]/g, "\\$&"); // regexp escape
	const re = new RegExp(`^${w.replace(/\*/g, ".*").replace(/\?/g, ".")}$`, "i");
	return re.test(str); // remove last 'i' above to have case sensitive
}

function updateOrCreateStreamers(streamers) {
	//Remove GroupFilter
	const streamerTemplate = qs("#template_streamer");
	
	streamers.sort((a, b) => {
		if (a.username.toLowerCase() < b.username.toLowerCase()) {
			return -1;
		}
		if (a.username.toLowerCase() > b.username.toLowerCase()) {
			return 1;
		}
		if (a.site.toLowerCase() < b.site.toLowerCase()) {
			return -1;
		}
		if (a.site.toLowerCase() > b.site.toLowerCase()) {
			return 1;
		}
		return 0;
	});
	let listOfStreamer = [];
	for (streamer of streamers) {
		let streamerID = "streamer_" + streamer.site + "_" + streamer.username;
		listOfStreamer.push(streamerID);

		let streamerNode = qs("#" + streamerID);

		if (!streamerNode) {
			let streamerImportNode = document.importNode(
				streamerTemplate.content,
				true
			);
			streamerNode = qs(".streamer-card", streamerImportNode);
			streamerNode.setAttribute("id", streamerID);
			streamerNode.setAttribute("site", streamer.site);
			streamerNode.setAttribute("username", streamer.username);
			
			// Add Bootstrap column classes for responsive grid
			streamerNode.classList.add("col-lg-4", "col-md-6", "col-sm-12");
			
			qs("#streamerGrid").appendChild(streamerNode);
		}
		
		// Clear existing status classes
		streamerNode.classList.remove("inactive", "downloading", "notDownloading", "onlineButNotDownlading", "private", "online", "offline", "recording");
		
		// Add status classes
		streamerNode.classList.toggle("inactive", !streamer.running);
		streamerNode.classList.toggle("downloading", streamer.sc == 200 && streamer.gStat == 1);
		streamerNode.classList.toggle("notDownloading", streamer.sc != 200 || streamer.gStat == 0);
		streamerNode.classList.toggle("onlineButNotDownlading", streamer.sc == 200 && streamer.gStat == 0);
		streamerNode.classList.toggle("private", streamer.sc == 403);
		streamerNode.classList.toggle("recording", streamer.running && streamer.recording);
		
		// Add additional status classes for styling
		if (streamer.running && streamer.recording) {
			streamerNode.classList.add("recording");
		} else if (streamer.sc == 200 && streamer.gStat == 1) {
			streamerNode.classList.add("downloading");
		} else if (streamer.sc == 200) {
			streamerNode.classList.add("online");
		} else if (streamer.sc == 403) {
			streamerNode.classList.add("private");
		} else {
			streamerNode.classList.add("offline");
		}

		streamerNode.classList.add("site_" + streamer.site);
		qs(".streamer_name", streamerNode).innerText = streamer.username;
		qs(".streamer_site", streamerNode).innerText = streamer.site;
		let website = qs(".streamer_url", streamerNode);
		if (streamer.url != "") {
			website.href = streamer.url;
		}

		qs(".streamer_site", streamerNode).setAttribute(
			"title",
			streamonitorSettings.sites[streamer.site]
		);
		
		// Format status with badge
		const statusElement = qs(".streamer_status", streamerNode);
		let statusClass = "status-offline";
		let statusText = streamer.status;
		
		if (streamer.running && streamer.recording) {
			statusClass = "status-recording";
			statusText = "🔴 Recording";
		} else if (streamer.sc == 200 && streamer.gStat == 1) {
			statusClass = "status-downloading";
			statusText = "🔴 Downloading";
		} else if (streamer.sc == 200) {
			statusClass = "status-online";
			statusText = "🟡 Online";
		} else if (streamer.sc == 403) {
			statusClass = "status-private";
			statusText = "🔒 Private";
		} else if (streamer.sc >= 400) {
			statusClass = "status-error";
			statusText = "❌ Error";
		}
		
		statusElement.innerHTML = `<span class="status-badge ${statusClass}">${statusText}</span>`;
	}

	qsa(".streamer-card").forEach((streamer) => {
		if (!listOfStreamer.includes(streamer.id)) {
			streamer.remove();
		}
	});
}

function updateFreespace(freeSpace) {
	const freeSpaceAbsolute = qs("#freeSpaceAbsolute");
	const freeSpacePercentage = qs("#freeSpacePercentage");
	freeSpaceAbsolute.innerText = freeSpace.absolute;
	freeSpacePercentage.innerText = freeSpace.percentage;
}

function getSortedKeysFromObject(obj) {
	let keys = [];

	for (let k in obj) {
		if (obj.hasOwnProperty(k)) {
			keys.push(k);
		}
	}
	keys.sort();
	return keys;
}

function fillSiteLists(sites) {
	const siteFilter = qs("#siteFilter");
	const streamerModal_site = qs("#streamerModal_site");
	const keys = getSortedKeysFromObject(sites);
	keys.forEach((siteslug) => {
		let sitename = sites[siteslug];
		if (!qs("#siteFilter_" + siteslug)) {
			var option = document.createElement("option");
			option.id = "siteFilter_" + siteslug;
			option.text = sitename;
			option.value = siteslug;
			siteFilter.appendChild(option);
		}
		if (!qs("#streamerModal_site_" + siteslug)) {
			var option = document.createElement("option");
			option.id = "streamerModal_site_" + siteslug;
			option.text = sitename;
			option.value = siteslug;
			streamerModal_site.appendChild(option);
		}
	});
}

function fillStatusFilter(status) {
	const statusFilter = qs("#realStatusFilter");
	for (const [id, statusname] of Object.entries(status)) {
		if (!qs("#realStatusFilter_" + id)) {
			var option = document.createElement("option");
			option.id = "realStatusFilter_" + id;
			option.text = statusname;
			option.value = id;
			statusFilter.appendChild(option);
		}
	}
}

function createStreamerElement(streamer) {
	qsa("#logins .meeting.gridElement").forEach((elem) => {
		elem.remove();
	});
	const loginTemplate = qs("#meetingItemTemplate");
	for (const [label, logindata] of Object.entries(getLogins())) {
		let loginDataNode = document.importNode(loginTemplate.content, true);
		qs(".meeting", loginDataNode).setAttribute("label", logindata.label);
		qs(".meeting_label", loginDataNode).innerText = logindata.label;
		qs(".meeting_info", loginDataNode).innerText =
			"Name: " + logindata.loginname;
		qs("#logins").insertBefore(
			loginDataNode,
			document.getElementById("addmeeting")
		);
	}
}

function createStreamer() {
	const modal = new bootstrap.Modal(qs("#streamerModal"));
	qs("#streamerModal_username").disabled = false;
	qs("#streamerModal_username").value = "";
	qs("#streamerModal_site").disabled = false;
	qs("#streamerModal_site").selectedIndex = 0;
	modal.show();
}

function saveStreamer() {
	let username = qs("#streamerModal_username").value;
	let site = qs("#streamerModal_site").value;
	let command = "add " + username + " " + site;
	sendCommand(command);
	
	const modal = bootstrap.Modal.getInstance(qs("#streamerModal"));
	modal.hide();
}

function closeStreamerModal() {
	const modal = bootstrap.Modal.getInstance(qs("#streamerModal"));
	modal.hide();
}

function startStreamers() {
	sendMultiCommand("start", getVisibleStreamers());
}

function stopStreamers() {
	sendMultiCommand("stop", getVisibleStreamers());
}

function sendMultiCommand(command, streamers) {
	streamers.forEach((streamerNode) => {
		let username = streamerNode.getAttribute("username");
		let site = streamerNode.getAttribute("site");
		sendCommand(command + " " + username + " " + site);
	});
}

function getVisibleStreamers() {
	let streamer = [];
	qsa(".streamer-card").forEach((streamerNode) => {
		if (streamerNode.style.display != "none") {
			streamer.push(streamerNode);
		}
	});
	return streamer;
}

function showSnackbarMessage(message, onlyAddWhenNoMessage = false) {
	const toastElement = qs("#snackbar");
	const toastBody = toastElement.querySelector(".toast-body");
	
	if (toastBody.innerHTML.trim() === "" || !onlyAddWhenNoMessage) {
		toastBody.innerHTML = message;
		
		const toast = new bootstrap.Toast(toastElement, {
			autohide: true,
			delay: 3000
		});
		
		toast.show();
	}
}

function deleteFilter() {
	qs("#streamerFilter").value = "";
	qs("#siteFilter").value = "";
	qs("#statusFilter").value = "";
	filterStreamers();
}