'''
Copyright 2023 i-PRO Co., Ltd.
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
    http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
'''

##########
#
# i-PRO AI検査アプリケーション(MS-EXFANS01A) 用SpeeDBee Hiveカスタムコレクタ
# SpeeDBee Hive Custom Collector for i-PRO AI Inspection Application (MS-EXFANS01A)
#
#   AI検査アプリケーションによる検査結果を指定フォルダのファイルから取得し、SpeeDBee Hiveに登録するサンプルソフトとなります
#   This is a sample software that acquires inspection results by AI inspection application from a file in a specified folder and registers them in SpeeDBee Hive.
#
#   Requirements:
#       株式会社ソルティスター SpeeDBee
#           Hive https://www.saltyster.com/
# 
#   Environment:
#        本サンプルは、以下環境で動作確認をおこなっています。
#            SpeeDBeeHive  v3.16.2
#            MS-EXFANS01A  v1.00
#
#   Usage:
#       SpeeDB Hiveのカスタムコレクターに登録してください。
#       登録方法は、SpeeDB Hiveのマニュアルを参照してください。
#       登録する際に、パラメータに検査結果の格納フォルダとチェック結果の格納フォルダを半角スペースで区切って指定してください。
#       （例) パラメータ : C:/data c:/tmp
#
#   Note:
#       本サンプルはSpeeDBee HiveとMS-EXFANS01Aとの連携を試験的に確認するためのサンプルソフトであり、一切の動作保証を致しません。
#       使用者の自己責任の元でご使用ください。
#       This sample is for testing the linkage between SpeeDBee Hive and MS-EXFANS01A, and we do not guarantee any operation.
#       Use at user's own risk.
#
#       SpeeDBeeは株式会社ソルティスターの登録商標です。
#       SpeeDBee is a registered trademark of Soltistar.
#       
#   Author:
#       Ozawa Kazuya (小澤 和哉)
#
#   History:
#       2023/03/16 ver 1.00 初版
##########
from hive_collector import HiveCollectorBase, HiveColumn
import os
import pathlib
import json

# データチェック間隔(秒)
_intervalSec = 10

# 検査結果の取り込み上限
# 機種数
_max_modelnum = 10
# 機種毎のカメラ数
_max_camnum = 10
# 検査エリア数
_max_areanum = 10

# 検査結果が格納されているフォルダ
_resultDir = "result"
_judgeDir = "judge"

# 検査結果チェック状況を格納するフォルダ・ファイル
_infoDir = "aiinspect"
_infoFile = "aiinspect_info_%s.txt"


class HiveCollector(HiveCollectorBase):
    ##########
    #   初期化
    #
    #   Note:
    #       DB項目を定義する
    #       param : 検査結果格納フォルダ名
    ##########
    def __init__(self, param):
        # 引数
        dirs = param.split(" ")
        self.rootPath = dirs[0]
        self.infoPath = dirs[1]

        # DB定義
        # カメラ名
        self.clm0 = self.makeOutputColumn("cam",  HiveColumn.TypeString)
        # 検査日付
        self.clm1 = self.makeOutputColumn("date",  HiveColumn.TypeString)
        # ロット番号
        self.clm2 = self.makeOutputColumn("lot",  HiveColumn.TypeString)
        # 総合判定
        self.clm3 = self.makeOutputColumn("overallresult",  HiveColumn.TypeString)
        # エリア毎の判定結果
        self.clm4 = self.makeOutputColumn("result",  HiveColumn.TypeString)


    ##########
    #   メイン処理
    #
    #   Note:
    #       定期タイマー起動
    ##########
    def mainloop(self):
        # 設定した秒数毎にタイマーを起動する
        self.intervalCall(int(_intervalSec * 1000 * 1000), self.proc)


    ##########
    #   定期実行関数
    #
    #   Note:
    ##########
    def proc(self, ts, skip):
        # チェック関数呼び出し
        self.searchInspectResult()

    ##########
    #   検査結果チェック状況の読み込み
    #
    #   Note:
    #       前回チェックしたフォルダ名、ファイル名を取得する
    #       ファイルは、
    #       1 - カメラ数行      日付フォルダ名
    #       カメラ数行 -        検査結果ファイル名(json)
    ##########
    def getInspectDate(self, modelidx, folder_dates, file_dates):
        # カレントディレクトリに存在するチェック状況ファイル名
        infoFile = self.infoPath + "/" + _infoDir + "/" + _infoFile % (str(modelidx).zfill(2))

        try:
            # ファイルオープン
            with open(infoFile, mode='r') as f:
                # ファイル全行読み込み
                dates = f.readlines()
                for idx, date in enumerate(dates):
                    # 最初のカメラ数分は日付フォルダ名
                    if (_max_camnum > idx):
                        folder_dates[idx] = date.rstrip('\n')
                    # その後は検査結果ファイル名
                    else:
                        file_dates[idx - _max_camnum] = date.rstrip('\n')

        except FileNotFoundError as e:
            # ファイルが存在しない場合は、作成する
            self.setInspectDate(modelidx, folder_dates, file_dates)

        except Exception as e:
            self.logger.info(e)


    ##########
    #   検査結果チェック状況の書き込み
    #
    #   Note:
    #       配列の内容をファイルに出力する
    ##########
    def setInspectDate(self, modelidx, folder_dates, file_dates):
        # カレントディレクトリに存在するチェック状況ファイル名
        infoFile = self.infoPath + "/" + _infoDir + "/" + _infoFile % (str(modelidx).zfill(2))

        try:
            # ファイルオープン
            with open(infoFile, mode='w') as f:
                    # 最初のカメラ数分は日付フォルダ名
                for date in folder_dates:
                    f.write(date + "\n")
                    # その後は検査結果ファイル名
                for date in file_dates:
                    f.write(date + "\n")

        except Exception as e:
            self.logger.info(e)


    ##########
    #   検査結果をチェックする
    #
    #   Note:
    ##########
    def searchInspectResult(self):
        # 検査結果チェックの状況を保存するフォルダを作成
        try:
            os.mkdir(self.infoPath + "/" + _infoDir)
        except:
            # 既にある場合はエラーになるので無視する
            pass

        try:
            # モデルのフォルダ一覧を取得
            modelDirs = os.listdir(self.rootPath)
            modelDirs.sort()

            for modelidx, modelDir in enumerate(modelDirs):
                # 上限値を超えたら終了
                if (modelidx >= _max_modelnum):
                    return
                
                # モデルフォルダ、ログフォルダは除外
                if ("default" == modelDir or "log" == modelDir):
                    continue

                # チェック結果を格納する変数を生成
                folder_dates =  ["" for camno in range(_max_camnum)]
                file_dates =  ["" for camno in range(_max_camnum)]

                # 前回のチェック結果を取得
                self.getInspectDate(modelidx, folder_dates, file_dates)

                # カメラフォルダの一覧を取得
                modelPath = self.rootPath + "/" + modelDir
                camDirs = os.listdir(modelPath)
                camDirs.sort()

                for camidx, camDir in enumerate(camDirs):
                    # 検査結果の日付フォルダ一覧を取得
                    resultPath = modelPath + "/" + camDir + "/" + _resultDir
                    dateDirs = os.listdir(resultPath)
                    dateDirs.sort()

                    for dateidx, dateDir in enumerate(dateDirs):
                        # 前回チェックしたフォルダの日付と同じか新しいフォルダならチェックする
                        if (folder_dates[camidx] <= dateDir):
                            # 最終チェックしたフォルダの日付を更新
                            folder_dates[camidx] = dateDir

                            # 検査結果ファイルの一覧を取得
                            judgePath = resultPath + "/" + dateDir + "/" + _judgeDir
                            jsonFiles = os.listdir(judgePath)
                            jsonFiles.sort()

                            for jsonFile in jsonFiles:
                                # 前回チェックしたファイル名の日付より新しいファイル名ならチェックする
                                if (file_dates[camidx] < jsonFile):
                                    file_dates[camidx] = jsonFile

                                    # 検査結果ファイルオープン
                                    with open(judgePath + "/" + jsonFile, 'r') as fileH:
                                        # json形式で読み込み
                                        jsonH = json.load(fileH)

                                        # 総合判定結果取得(OK=0, NG=1)
                                        overallresult = ""
                                        if ("OK" == jsonH["overallResult"]):
                                            overallresult = "0"
                                        else:
                                            overallresult = "1"

                                        # エリア毎の判定結果取得(OK=0, NG=1)
                                        result = ""
                                        for areano in range(_max_areanum):
                                            if areano >= len(jsonH["detect"]):
                                                break
                                            if ("OK" == jsonH["detect"][areano]["judge"]):
                                                result = result + "0"
                                            else:
                                                result = result + "1"

                                        # DBに生成したデータを登録
                                        nowTime = self.getTimestamp()
                                        self.clm0.insert(camDir, nowTime)
                                        self.clm1.insert(jsonH["camDate"]["DATE"], nowTime)
                                        self.clm2.insert(modelDir, nowTime)
                                        self.clm3.insert(overallresult, nowTime)
                                        self.clm4.insert(result, nowTime)

                                        # 更新したチェック結果を保存
                                        self.setInspectDate(modelidx, folder_dates, file_dates)
                                        return
                        else:
                            # 前回チェックしたフォルダの日付より古いフォルダはスキップする
                            continue
                else:
                    continue

        except Exception as e:
            self.logger.info(e)
