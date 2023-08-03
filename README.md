# Googleの生成AI、PaLM 2をSlack連携して社内ツールとして導入してみた

このアーキテクチャでは App Engine が中継サーバとして機能し、Slack と PaLM 2 間の通信をスムーズに行います。具体的には Flask フレームワークを用いた Python アプリケーションが、Slack からのメッセージ (プロンプト) を受け取り、それを PaLM 2 に転送します。その後、PaLM 2 からの応答 (レスポンス) を取得して Slack へ返します。

## 特徴

- Secret Manager を活用して、認証済みサービスアカウントにアタッチされた App Engine の Python アプリケーションへとシークレット情報をセキュアに提供します。
- Python アプリケーションは、ユーザーのプロンプトと PaLM 2 からのレスポンスを Cloud Logging へ記録します。Cloud Logging はログデータをログバケットに保存し、それを BigQuery へ自動的に同期するように設定します。これにより、管理者はプロンプトと応答の履歴を簡単に分析することができます。

このコードは株式会社G-genにより提供されています。

## デプロイ方法

1. Cloud Shellでこのリポジトリをクローンします。
   ```
   git clone https://github.com/G-gen-Tech-Blog/using-palm2-with-slack-chat-bot.git
   ```

2. `gcloud app deploy` コマンドでデプロイします。
   ```
   gcloud app deploy
   ```
