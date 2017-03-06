namespace = '/celery';
socket = io.connect('http://' + document.domain + ':' + location.port + namespace);

socket.on('connect', function() {
	$('#log').append('Connected<br>');
});

socket.on('log processing', function(msg) {
	if (msg.data.STARTING){
		console.log('Starting: ' + msg.data.STARTING);
		var log_id = msg.data.STARTING.log
		var status_btn = document.getElementById(log_id+'_btn');
		remove_button_class(status_btn)
		status_btn.classList.add('btn-info');
        $('#log').append('Starting: ' + msg.data.STARTING + '<br>');
        
	} else if (msg.data.PROGRESS) {
		console.log('Progress: ' + msg.data.PROGRESS);
		var log_id = msg.data.PROGRESS.log
		var pct = msg.data.PROGRESS.current
		var status_btn = document.getElementById(log_id+'_btn');
		status_btn.innerHTML='PROCESSING<br>'+pct+'%'
		remove_button_class(status_btn)
		status_btn.classList.add('btn-info');
		$('#log').append('Progress: ' + msg.data.PROGRESS + '<br>');
		
 
	} else if (msg.data.COMPLETE) {
		console.log('Complete: ' + msg.data.COMPLETE);
		var log_id = msg.data.COMPLETE.log
		var status_btn = document.getElementById(log_id+'_btn');
		status_btn.innerHTML='COMPLETE'
		remove_button_class(status_btn)
		status_btn.classList.add('btn-success');
		$('#log').append('Complete: ' + msg.data.COMPLETE + '<br>');
        
	} else if (msg.data.ERROR) {
		var log_id = msg.data.ERROR.log
		var status_btn = document.getElementById(log_id+'_btn');
		status_btn.innerHTML='ERROR'
		remove_button_class(status_btn)
		status_btn.classList.add('btn-danger');
		console.log('Error: ' + msg.data.ERROR);
        $('#log').append('Error: ' + msg.data.ERROR + '<br>');

	} else {
		console.log('Unhandled log status');
	}
});

function remove_button_class(btn) {
	if ( btn.classList.contains('btn-success') ) {
		btn.classList.remove('btn-success');
		
	} else if ( btn.classList.contains('btn-info') ) {
		btn.classList.remove('btn-info');
		
	} else if ( btn.classList.contains('btn-danger') ) {
		btn.classList.remove('btn-danger');
		
	}  else if ( btn.classList.contains('btn-default') ) {
		btn.classList.remove('btn-default');
		
	} else {
		console.log('Unhandled button class');
	}
};
