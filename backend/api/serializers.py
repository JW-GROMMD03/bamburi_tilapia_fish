from rest_framework import serializers

class TransactionItemSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    price = serializers.IntegerField()
    qty = serializers.IntegerField(default=1)

class TransactionSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    date = serializers.DateField()
    time = serializers.CharField(max_length=20)
    total = serializers.IntegerField()
    method = serializers.CharField(max_length=10)
    cashAmt = serializers.IntegerField(default=0)
    mpesaAmt = serializers.IntegerField(default=0)
    items = TransactionItemSerializer(many=True)
    created_at = serializers.DateTimeField(read_only=True)
    #created_downtime = serializers.DateTimeField(read_only=True)

class ExpenseSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    date = serializers.DateField()
    time = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=200)
    amount = serializers.IntegerField()
    created_at = serializers.DateTimeField(read_only=True)

class TrashItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    item_type = serializers.CharField(max_length=10)
    description = serializers.CharField(max_length=500)
    data = serializers.JSONField()
    trashed_at = serializers.DateTimeField(read_only=True)