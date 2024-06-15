from flask import Flask, render_template, request, redirect, url_for, jsonify
import os
# from C20240415RC.test_IEEE_TNNLS_Gia_CFSL_main.IEEE_TNNLS_Gia_CFSL_main import demo_test_v1_0
import demo_test_v1_0

# Flask应用程序，实现了一个简单的文件上传功能和图像处理功能

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/display')
def display():
    return render_template('display.html')

from werkzeug.utils import secure_filename
import matplotlib.pyplot as plt
import scipy.io as sio

@app.route('/upload', methods=['POST'])
def upload_image():
    if 'image' in request.files:
        file = request.files['image']
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # 处理.mat文件
        mat_contents = sio.loadmat(file_path)
        print(mat_contents.keys())

        image = mat_contents['paviaU'][:,:,3]  # 替换为.mat文件中的变量名
        print(image.shape)
        plt.figure(figsize=(3,6))
        plt.imshow(image)
        sourcePath='static/mat_image.png'
        plt.savefig(sourcePath)


        # 假设分类和颜色图例的处理逻辑已经实现
        result_image_path = 'predictImage.png'  # 假设这是处理后的结果图像路径

        demo_test_v1_0.main("D:\pythoncode//test-IEEE_TNNLS_Gia-CFSL-main\IEEE_TNNLS_Gia-CFSL-main\item//"+file_path,"static/"+result_image_path)
        # return make_response({mat_image: 'mat_image.png', result_image: result_image_path}, 200)
        return jsonify({'mat_image': 'mat_image.png', 'result_image': result_image_path})
        return render_template('display.html', mat_image='mat_image.png', result_image=result_image_path)
    return redirect(url_for('index'))



if __name__ == '__main__':
    app.run(host="0.0.0.0",port=5001)
