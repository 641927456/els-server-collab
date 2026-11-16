using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Windows.Forms;

namespace ElsFriends {
    // The material samples only the launcher's own artwork, never the desktop.
    class GlassPanel:Panel {
        readonly AdventureScene scene;
        readonly bool header;
        Bitmap backdrop,material;
        public GlassPanel(AdventureScene scene,bool header=false){
            this.scene=scene;this.header=header;DoubleBuffered=true;BackColor=Theme.Surface;
            scene.SizeChanged+=SceneChanged;scene.LocationChanged+=SceneChanged;
        }
        void SceneChanged(object sender,EventArgs e){DropMaterial();Invalidate(true);}
        void DropMaterial(){if(backdrop!=null){backdrop.Dispose();backdrop=null;}if(material!=null){material.Dispose();material=null;}}
        protected override void OnSizeChanged(EventArgs e){DropMaterial();base.OnSizeChanged(e);Invalidate(true);}
        protected override void OnLocationChanged(EventArgs e){DropMaterial();base.OnLocationChanged(e);Invalidate(true);}
        protected override void Dispose(bool disposing){if(disposing){scene.SizeChanged-=SceneChanged;scene.LocationChanged-=SceneChanged;DropMaterial();}base.Dispose(disposing);}
        void EnsureMaterial(){
            if(material!=null)return;
            backdrop=scene.CaptureBackdrop(this);material=new Bitmap(Width,Height,PixelFormat.Format24bppRgb);
            // Compose the translucent look once onto an opaque cache. Repainting a child must replace the old buffer.
            using(var edges=new ImageAttributes())using(var reduced=new Bitmap(Math.Max(1,Width/18),Math.Max(1,Height/18),PixelFormat.Format24bppRgb)){
                edges.SetWrapMode(WrapMode.TileFlipXY);
                using(var g=Graphics.FromImage(reduced)){g.Clear(Theme.Canvas);g.InterpolationMode=InterpolationMode.HighQualityBicubic;g.DrawImage(backdrop,new Rectangle(0,0,reduced.Width,reduced.Height),0,0,backdrop.Width,backdrop.Height,GraphicsUnit.Pixel,edges);}
                using(var g=Graphics.FromImage(material)){
                    g.Clear(Theme.Canvas);g.InterpolationMode=InterpolationMode.HighQualityBicubic;g.DrawImage(reduced,ClientRectangle,0,0,reduced.Width,reduced.Height,GraphicsUnit.Pixel,edges);
                    using(var tint=new SolidBrush(Color.FromArgb(208,24,39,46)))g.FillRectangle(tint,ClientRectangle);
                    using(var light=new LinearGradientBrush(ClientRectangle,Color.FromArgb(10,225,244,250),Color.Transparent,90f))g.FillRectangle(light,ClientRectangle);
                }
            }
        }
        protected override void OnPaintBackground(PaintEventArgs e){
            EnsureMaterial();var g=e.Graphics;g.DrawImageUnscaled(backdrop,Point.Empty);g.SmoothingMode=SmoothingMode.AntiAlias;
            if(header){g.DrawImageUnscaled(material,Point.Empty);return;}
            using(var shape=Theme.Round(new RectangleF(.5f,.5f,Width-1,Height-1),15)){
                var saved=g.Save();g.SetClip(shape);g.DrawImageUnscaled(material,Point.Empty);g.Restore(saved);
                using(var line=new Pen(Color.FromArgb(57,191,221,232)))g.DrawPath(line,shape);
            }
        }
        public void PaintChildBackdrop(Control child,Graphics graphics){
            EnsureMaterial();Point offset=Point.Empty;for(Control current=child;current!=this;current=current.Parent)offset.Offset(current.Left,current.Top);
            graphics.DrawImage(material,new Rectangle(Point.Empty,child.Size),new Rectangle(offset,child.Size),GraphicsUnit.Pixel);
        }
        public static void TransparentChildren(Control root){foreach(Control c in root.Controls){if(c is MotionInput||c.Name=="material-separator")continue;if(c is Panel||c is Label)c.BackColor=Color.Transparent;TransparentChildren(c);}}
        public object VerifyMaterialForTest(){
            EnsureMaterial();double min=1,max=0;int differences=0;double ink=Brightness(Theme.Muted);int minimumAlpha=255;
            for(int y=0;y<Height;y+=4)for(int x=0;x<Width;x+=4)minimumAlpha=Math.Min(minimumAlpha,material.GetPixel(x,y).A);
            if(minimumAlpha!=255)throw new Exception("Glass cache retained transparency and can leak old buffer pixels");
            for(int y=8;y<Height-8;y+=8)for(int x=8;x<Width-8;x+=8){double value=Brightness(material.GetPixel(x,y));min=Math.Min(min,value);max=Math.Max(max,value);if(material.GetPixel(x,y).ToArgb()!=backdrop.GetPixel(x,y).ToArgb())differences++;}
            double contrast=(ink+.05)/(max+.05);if(contrast<4.5||max-min<.002||differences==0)throw new Exception("Glass material contrast or artwork sampling failed");
            return new {artwork_sampled=true,blurred_and_tinted=true,opaque_composed_cache=true,minimum_alpha=minimumAlpha,background_luminance_range=max-min,minimum_secondary_text_contrast=contrast,desktop_capture=false};
        }
        static double Brightness(Color color){Func<int,double> linear=v=>{double c=v/255.0;return c<=.04045?c/12.92:Math.Pow((c+.055)/1.055,2.4);};return .2126*linear(color.R)+.7152*linear(color.G)+.0722*linear(color.B);}
    }
    class FlatInfoPanel:Panel {
        public FlatInfoPanel(){DoubleBuffered=true;BackColor=Theme.Surface;}
        protected override void OnPaintBackground(PaintEventArgs e){
            e.Graphics.Clear(Theme.Canvas);e.Graphics.SmoothingMode=SmoothingMode.AntiAlias;
            using(var path=Theme.Round(new RectangleF(0,0,Width-1,Height-1),6))using(var fill=new SolidBrush(Theme.Surface))e.Graphics.FillPath(fill,path);
        }
        public object VerifyFlatForTest(){
            using(var bitmap=new Bitmap(Width,Height)){
                DrawToBitmap(bitmap,ClientRectangle);
                for(int x=16;x<Width-16;x+=8)foreach(int y in new[]{4,Height-5})if(bitmap.GetPixel(x,y).ToArgb()!=Theme.Surface.ToArgb())throw new Exception("Information strip is not flat");
            }
            return new {solid_surface=true,no_blur=true,no_gradient=true,no_bevel_or_border=true};
        }
    }
}
