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
		loadStreamers();
	});

	addGlobalEventListener("click", ".streamer_delete", (e) => {
		const streamer = e.target.closest(".streamer");
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
		const streamer = e.target.closest(".streamer");
		let command =
			"start " +
			streamer.getAttribute("username") +
			" " +
			streamer.getAttribute("site");
		sendCommand(command);
	});

	addGlobalEventListener("click", ".streamer_stop", (e) => {
		const streamer = e.target.closest(".streamer");
		let command =
			"stop " +
			streamer.getAttribute("username") +
			" " +
			streamer.getAttribute("site");
		sendCommand(command);
	});

	addGlobalEventListener("click", ".streamer_edit", (e) => {
		const streamer = e.target.closest(".streamer");

		qs("#streamerModal_username").disabled = true;
		qs("#streamerModal_username").value = streamer.getAttribute("username");
		qs("#streamerModal_site").disabled = true;
		qs("#streamerModal_site").value = streamer.getAttribute("site");
		qs("#streamerModal").classList.add("show");
	});

	loadStreamers();
	setInterval(function () {
		loadStreamers();
	}, 3000);
}

function filterStreamers() {
	const streamer = qsa(".streamer");
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
		qs("#countStreamer").innerText = "[" + counterText + "]";
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
			streamerNode = qs(".streamer", streamerImportNode);
			streamerNode.setAttribute("id", streamerID);
			streamerNode.setAttribute("site", streamer.site);
			streamerNode.setAttribute("username", streamer.username);
			qs("#streamerGrid").appendChild(streamerNode);
		}
		streamerNode.classList.toggle("inactive", !streamer.running);
		streamerNode.classList.toggle(
			"downloading",
			streamer.sc == 200 && streamer.gStat == 1
		);
		streamerNode.classList.toggle(
			"notDownloading",
			streamer.sc != 200 || streamer.gStat == 0
		);
		streamerNode.classList.toggle(
			"onlineButNotDownlading",
			streamer.sc == 200 && streamer.gStat == 0
		);
		streamerNode.classList.toggle("private", streamer.sc == 403);

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
		qs(".streamer_status", streamerNode).innerText = streamer.status;
	}

	qsa(".streamer").forEach((streamer) => {
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
	qs("#streamerModal").classList.add("show");
	qs("#streamerModal_username").disabled = false;
	qs("#streamerModal_username").value = "";
	qs("#streamerModal_site").disabled = false;
}

function saveStreamer() {
	let username = qs("#streamerModal_username").value;
	let site = qs("#streamerModal_site").value;
	let command = "add " + username + " " + site;
	sendCommand(command);
	closeStreamerModal();
}

function closeStreamerModal() {
	qs("#streamerModal").classList.remove("show");
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
	qsa(".streamer").forEach((streamerNode) => {
		if (streamerNode.style.display != "none") {
			streamer.push(streamerNode);
		}
	});
	return streamer;
}

function showSnackbarMessage(message, onlyAddWhenNoMessage = false) {
	window.clearTimeout(window.snackbarTimeout);
	let snackbar = qs("#snackbar");
	if (snackbar.innerHTML == "" || !onlyAddWhenNoMessage) {
		snackbar.innerHTML = snackbar.innerHTML + message + "<br />";
	}
	snackbar.className = "show";
	window.snackbarTimeout = setTimeout(function () {
		snackbar.innerHTML = "";
		snackbar.className = snackbar.className.replace("show", "");
	}, 5000);
}

function deleteFilter() {
	qs("#streamerFilter").value = "";
	qs("#siteFilter").value = "";
	qs("#statusFilter").value = "";
	filterStreamers();
}