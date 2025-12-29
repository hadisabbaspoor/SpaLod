from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.db.models import Q

class UploadedFile(models.Model):
    file = models.FileField(upload_to='uploads/')
    metadata = models.JSONField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

class FlyvastPointcloud(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    pc_id = models.CharField(max_length=512)


class VocabularyMapping(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vocab_mappings')
    dataset_iri = models.CharField(max_length=500)
    original_uri = models.CharField(max_length=500)
    new_uri = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        unique_together = ('user', 'dataset_iri', 'original_uri')
        constraints = [
        models.CheckConstraint(
            name='vocab_new_uri_http_or_null',
            check=Q(new_uri__isnull=True) | Q(new_uri__startswith='http'),
        ),
    ]