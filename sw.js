self.addEventListener('push', function(event) {
    const data = event.data ? event.data.json() : { title: 'Новое сообщение', body: 'У вас новое сообщение' };
    
    const options = {
        body: data.body,
        icon: '/static/icon.png', // путь к вашей иконке
        badge: '/static/badge.png'
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});
